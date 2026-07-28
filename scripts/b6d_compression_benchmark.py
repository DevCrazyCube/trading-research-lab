#!/usr/bin/env python3
"""Streaming, per-segment compression throughput benchmark (no output files)."""
import argparse
import lzma
import os
import time
import zlib


def segments(root):
    for directory, _, files in os.walk(os.path.join(root, "segments")):
        for name in sorted(files):
            if name.endswith(".seg"):
                yield os.path.join(directory, name)


def compress_one(path, algorithm):
    if algorithm == "zlib-6":
        compressor = zlib.compressobj(6)
    elif algorithm == "lzma-1":
        compressor = lzma.LZMACompressor(preset=1)
    else:
        raise ValueError(algorithm)
    source = output = 0
    started = time.perf_counter()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            source += len(chunk)
            output += len(compressor.compress(chunk))
    output += len(compressor.flush())
    elapsed = time.perf_counter() - started
    return source, output, elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    paths = list(segments(args.root))
    if not paths:
        raise SystemExit("no .seg files found")
    for algorithm in ("zlib-6", "lzma-1"):
        total_in = total_out = 0
        total_seconds = 0.0
        for path in paths:
            source, output, elapsed = compress_one(path, algorithm)
            total_in += source
            total_out += output
            total_seconds += elapsed
        mib = total_in / (1 << 20)
        print(f"{algorithm} segments={len(paths)} input_mib={mib:.3f} "
              f"ratio={total_in/total_out:.3f} throughput_mib_s={mib/total_seconds:.3f} "
              f"cpu_seconds={total_seconds:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
