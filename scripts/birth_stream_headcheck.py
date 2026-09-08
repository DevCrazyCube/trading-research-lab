"""Bounded finalized-head comparison. Raw RPC evidence retained; no trades or backfill."""
import argparse
import json
from pathlib import Path
import sqlite3
import time

from scripts.birth_origin import Refused, write_new
from scripts.birth_stream_verify import EvidenceRPC


def snapshot(path):
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        row = db.execute("SELECT last_notification_slot,last_notification_sequence FROM connection_epoch "
                         "WHERE last_notification_sequence IS NOT NULL ORDER BY last_notification_sequence DESC LIMIT 1").fetchone()
        if row is None:
            return {"source": str(path), "status": "NO_NOTIFICATION"}
        receipt = db.execute("SELECT received_unix_nanos FROM raw_frame WHERE sequence=?", (row[1],)).fetchone()[0]
        return {"source": str(path), "slot": row[0], "sequence": row[1], "receipt_unix_nanos": receipt,
                "sampled_unix_nanos": time.time_ns(), "status": "OBSERVED_NOT_CENSUS"}
    finally:
        db.close()


def run(sources, out, samples, interval):
    if out.exists() or not 1 <= samples <= 30 or not 0 <= interval <= 60:
        raise Refused("new output and bounded samples/interval required")
    out.mkdir(parents=True)
    rpc, rows = EvidenceRPC(out), []
    for index in range(samples):
        row = {"index": index, "started_unix_nanos": time.time_ns(), "before": [snapshot(p) for p in sources]}
        try:
            head = rpc.call("getSlot", [{"commitment": "finalized"}])
            if type(head) is not int or head < 0:
                raise Refused("invalid finalized head slot")
            row.update(finalized_head_slot=head, after=[snapshot(p) for p in sources],
                       comparison="before/after bracket around public RPC; not independent-provider consensus")
            row["slot_lag_brackets"] = [{"source": str(p),
                "head_minus_feed_before": head - before["slot"] if "slot" in before else None,
                "head_minus_feed_after": head - after["slot"] if "slot" in after else None}
                for p, before, after in zip(sources, row["before"], row["after"])]
        except Exception as error:
            row["error"] = type(error).__name__ + ": " + str(error)
        write_new(out / f"checkpoint_{index:03d}.json", row)
        rows.append(row)
        print(json.dumps(row), flush=True)
        if index + 1 < samples:
            time.sleep(interval)
    write_new(out / "result.json", {"status": "READ_ONLY_ENGINEERING_NO_TRADE", "checkpoints": rows,
                                   "creation_recall": "UNMEASURED", "missing_history": "NOT_REPAIRED"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--interval", type=float, default=30)
    args = parser.parse_args()
    run(args.source, args.out, args.samples, args.interval)
