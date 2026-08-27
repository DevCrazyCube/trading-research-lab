#!/usr/bin/env python3
"""Extract a point-in-time Deribit options-chain snapshot from a FREE Tardis sample.

ZERO SPEND: uses only the public first-day-of-month sample files, no account/key:
    https://datasets.tardis.dev/v1/deribit/options_chain/YYYY/MM/DD/OPTIONS.csv.gz

Each full-day file is ~1.2 GB compressed (tick-resolution, one row per quote change).
We do NOT store the whole day. We stream `curl | zcat`, keep the LAST row seen per
instrument with timestamp <= T_target, and stop once the stream has moved a safety
margin past T_target. The result is a proper point-in-time chain snapshot of a few
thousand rows, written gzipped under research/data/deribit_free_samples/.

Rows are roughly timestamp-sorted (Tardis guarantees non-decreasing local_timestamp
per file); we key off the exchange `timestamp` and use a +120s margin before halting.

USAGE:
    python3 scripts/trading_bot/deribit_free_snapshot.py 2023-06-01 [--minute 15]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import io
import pathlib
import subprocess
import sys

OUTDIR = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "deribit_free_samples"
URL_TMPL = "https://datasets.tardis.dev/v1/deribit/options_chain/{y:04d}/{m:02d}/{d:02d}/OPTIONS.csv.gz"
MARGIN_S = 120  # keep streaming this many seconds past T_target before stopping


def extract(date: str, minute: int) -> pathlib.Path:
    y, m, d = (int(x) for x in date.split("-"))
    url = URL_TMPL.format(y=y, m=m, d=d)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / f"snapshot_{date}_m{minute}.csv.gz"

    # stream: curl -> zcat -> line reader
    curl = subprocess.Popen(
        ["curl", "-sSL", "--retry", "4", "--retry-delay", "2",
         "--retry-connrefused", "--connect-timeout", "20", url],
        stdout=subprocess.PIPE)
    zcat = subprocess.Popen(["zcat"], stdin=curl.stdout, stdout=subprocess.PIPE)
    curl.stdout.close()  # allow curl to get SIGPIPE when we stop

    header: list[str] | None = None
    ts_idx = sym_idx = None
    # Anchor the snapshot clock to the LABELLED date, not the first row: some files
    # begin with a stray row timestamped 23:59:59.99x of the prior day, which would
    # otherwise mis-anchor day_start and break the stream after one row.
    day_start_us = int(dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp()) * 1_000_000
    t_target_us = day_start_us + minute * 60 * 1_000_000
    latest: dict[str, list[str]] = {}
    n_rows = 0

    reader = io.TextIOWrapper(zcat.stdout, encoding="utf-8")
    for line in reader:
        row = line.rstrip("\n").split(",")
        if header is None:
            header = row
            sym_idx = header.index("symbol")
            ts_idx = header.index("timestamp")
            continue
        n_rows += 1
        try:
            ts = int(row[ts_idx])  # microseconds
        except (ValueError, IndexError):
            continue
        if ts <= t_target_us:
            latest[row[sym_idx]] = row
        elif ts > t_target_us + MARGIN_S * 1_000_000:
            break

    # tear down the pipe
    try:
        reader.close()
    except Exception:
        pass
    for p in (zcat, curl):
        try:
            p.terminate()
        except Exception:
            pass
        try:
            p.wait(timeout=5)
        except Exception:
            pass

    if header is None or not latest:
        raise SystemExit(f"NO DATA for {date} (url={url}); rows_seen={n_rows}")

    with gzip.open(out, "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in latest.values():
            w.writerow(r)

    snap_dt = dt.datetime.fromtimestamp(t_target_us / 1e6, dt.timezone.utc)
    print(f"{date}: {len(latest)} instruments @ {snap_dt.isoformat()} "
          f"(streamed {n_rows} rows) -> {out.name}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("date", help="YYYY-MM-DD (must be first-of-month for the free sample)")
    ap.add_argument("--minute", type=int, default=15, help="snapshot wall-clock minute past 00:00 UTC")
    args = ap.parse_args()
    extract(args.date, args.minute)


if __name__ == "__main__":
    main()
