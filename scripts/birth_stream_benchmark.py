"""Bounded offline recorder profiling. No network, prices, strategy replay or fills."""
import argparse
from collections import defaultdict
import cProfile
import hashlib
import io
import json
from pathlib import Path
import pstats
import sqlite3
import tempfile
import time
import zlib

from scripts import birth_stream as BS
from scripts.birth_origin import Refused, write_new


def run(source, out, rows, batched=False):
    if out.exists() or not 1 <= rows <= 10000:
        raise Refused("new output and 1..10000 rows required")
    db = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        frames = [zlib.decompress(r[0]) for r in db.execute("SELECT raw_zlib FROM raw_frame ORDER BY sequence LIMIT ?", (rows,))]
    finally:
        db.close()
    idl, subscription, timings = BS.load_idl(), None, defaultdict(float)
    profile = cProfile.Profile()
    # Use the SAME filesystem as production. /tmp is tmpfs on this host and would
    # hide the actual cost of FULL synchronous disk commits.
    with tempfile.TemporaryDirectory(prefix="birth-offline-benchmark-", dir=out.parent) as directory:
        from scripts import birth_stream_fast as FAST
        rec_class = FAST.Recorder if batched else BS.Recorder
        rec = rec_class(Path(directory) / "temporary.sqlite", max_bytes=256 * 1024 ** 2)
        profile.enable()
        start = time.perf_counter()
        for index, raw in enumerate(frames):
            if batched:
                if index % FAST.BATCH_FRAMES:
                    continue
                before = time.perf_counter()
                items = [(item, time.time_ns(), time.monotonic_ns()) for item in frames[index:index + FAST.BATCH_FRAMES]]
                subscription, _ = rec.consume(items, idl, subscription, BS.B9D.event_entries(idl))
                rec.bytes_on_disk()
                BS.shutil.disk_usage(rec.path.parent)
                timings["batched_raw_decode_derived_capacity"] += time.perf_counter() - before
                continue
            before = time.perf_counter()
            rec.bytes_on_disk()
            BS.shutil.disk_usage(rec.path.parent)
            timings["capacity_checks"] += time.perf_counter() - before
            before = time.perf_counter()
            seq = rec.append(raw, time.time_ns(), time.monotonic_ns())
            timings["raw_commit"] += time.perf_counter() - before
            before = time.perf_counter()
            message = json.loads(raw)
            if subscription is None:
                subscription = message["result"]
                births, stats = [], {"subscription_ack": 1}
            else:
                births, stats = BS.decode_notification(message, idl, subscription)
            timings["decode"] += time.perf_counter() - before
            before = time.perf_counter()
            rec.materialize(seq, births, stats)
            timings["derived_commit"] += time.perf_counter() - before
            before = time.perf_counter()
            if stats == {"subscription_ack": 1}:
                rec.acknowledge(seq, subscription)
            else:
                rec.notification_received(seq, message["params"]["result"]["context"]["slot"], time.time_ns())
            timings["notification_commit"] += time.perf_counter() - before
        elapsed = time.perf_counter() - start
        profile.disable()
        rec.finish("OFFLINE_BENCHMARK_NOT_FORWARD_DATA")
    stream = io.StringIO()
    pstats.Stats(profile, stream=stream).sort_stats("tottime").print_stats(18)
    result = {"purpose": "OFFLINE_ENGINEERING_BENCHMARK_NOT_LIVE_OR_STRATEGY_DATA",
        "frames": len(frames), "seconds": elapsed, "frames_per_second": len(frames) / elapsed,
        "stages_seconds": dict(timings), "profile": stream.getvalue(), "source": str(source),
        "raw_prefix_sha256": hashlib.sha256(b"".join(frames)).hexdigest(),
        "recorder_sha256": hashlib.sha256(Path(FAST.__file__ if batched else BS.__file__).read_bytes()).hexdigest(),
        "batched": batched,
        "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "benchmark_filesystem_parent": str(out.parent),
        "temporary_database": "ephemeral timing fixture removed; not a recorded live cohort"}
    out.mkdir(parents=True)
    write_new(out / "result.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("research/midcap/birth_stream_pilot_network_20260908.sqlite"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=2000)
    parser.add_argument("--batched", action="store_true")
    args = parser.parse_args()
    run(args.source, args.out, args.rows, args.batched)
