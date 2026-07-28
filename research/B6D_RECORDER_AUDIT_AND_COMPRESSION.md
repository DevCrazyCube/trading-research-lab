# B6d — Recorder Audit and Streaming Compression Benchmark

Run: 2026-07-27. Offline audit/tests against `scripts/recorder.py` and the three B6-lite segments.

## Audit corrections

The first implementation demonstrated the recovery concept, but three claims required correction:

1. I3 requires `first_missing_hint = last_valid_seq + 1`; the implementation wrote
   `last_valid_seq`. This off-by-one is fixed and covered by a torn-tail recovery test.
2. `subscription_spec` included the literal RPC URL. A credential-bearing custom URL would have
   been persisted, violating the opaque-endpoint rule. It now records only `public-mainnet` or
   `configured-rpc`; the URL remains process-local.
3. JSON-RPC cannot server-filter Pump transactions. The polling adapter parses a block and emits
   normalized filtered JSON, so its payload is **not byte-identical to the HTTP provider frame**.
   It is now labelled `b6-lite-normalized-v1`. The pilot validates framing/recovery mechanics,
   not raw-provider fidelity. A Geyser adapter must store received protobuf bytes unchanged.

The UUID-shaped identifier helper was also replaced with a real 26-character Crockford ULID.

## Tests

`tests/test_recorder.py` verifies:

- the standard CRC32C vector (`123456789` → `e3069283`),
- ULID alphabet and length,
- two valid records plus a four-byte torn tail recover to `first_missing_hint = 2`, unknown end,
  a sealed segment, and a recorded crash gap.

All three tests pass.

## Streaming per-segment compression

`scripts/b6d_compression_benchmark.py` compresses each segment independently in 1 MiB chunks and
discards output. It neither concatenates segments nor holds the dataset in memory.

| Codec | Input | Ratio | Throughput | CPU time |
|---|---:|---:|---:|---:|
| zlib level 6 | 54.784 MiB | 10.148× | 30.084 MiB/s | 1.821 s |
| LZMA preset 1 | 54.784 MiB | 27.027× | 20.601 MiB/s | 2.659 s |

The JSON snapshot's projected full-rate input is about 241 GB/day, or roughly 2.66 MiB/s. On this
sample, zlib has ~11.3× throughput headroom and LZMA ~7.7×. Both pass the isolated compression
throughput precondition. This is **not** a codec decision: Geyser protobuf has different volume,
redundancy, message boundaries, and CPU interaction with decoding and disk writes.

## Decision impact

- Keep retention sizes and codec selection unfixed.
- Geyser remains mandatory because polling coverage was only ~14%.
- Re-run the same streaming benchmark on actual byte-identical Geyser segments while capture and
  decoding run concurrently; isolated throughput alone does not establish sustained duty cycle.
