"""Decode Codex's verified birth-stream capture into a full pump.fun trade tape.

The v3 capture (9.6M frames, 7.3h, 99.43% coverage, raw replay EXACT) subscribed to
the whole Pump program, so it holds every Buy/Sell TradeEvent for every coin born in
the window -- a survivorship-free tape with strictly time-ordered receipts.

Read-only over the capture. Reuses the pinned IDL and B9D event decoder that the
capture itself was verified with. New file; nothing under arena/ is touched.
"""
import base64, json, re, sqlite3, sys, time, zlib
from collections import Counter
from scripts import b9d_transaction_bodies as B9D
from scripts.birth_stream import load_idl

SRC = "research/midcap/birth_stream_forward_v3_20260908T1901.sqlite"
OUT = "research/midcap/tape_v3.sqlite"
INVOKE = re.compile(r"Program (\S+) invoke \[(\d+)\]")
ENDED = re.compile(r"Program (\S+) (success|failed:.*)")


def events_in(logs, entries):
    """Yield (log_index, payload) for Pump-program-parented Program data lines."""
    stack = []
    for i, line in enumerate(logs):
        m = INVOKE.fullmatch(line)
        if m:
            stack.append(m.group(1)); continue
        m = ENDED.fullmatch(line)
        if m:
            if stack: stack.pop()
            continue
        if not line.startswith("Program data:") or not stack or stack[-1] != B9D.PUMP_PROGRAM:
            continue
        try:
            payload = base64.b64decode(line[len("Program data:"):].strip(), validate=True)
        except ValueError:
            continue
        yield i, payload


def main(limit=None):
    idl = load_idl(); entries = B9D.event_entries(idl)
    src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
    out = sqlite3.connect(OUT)
    out.executescript("""
      PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;
      CREATE TABLE IF NOT EXISTS trade(
        seq INT, log_index INT, slot INT, sig TEXT, recv_ns INT, mint TEXT, is_buy INT,
        sol_amount INT, token_amount INT, user TEXT, ts INT, vsol INT, vtok INT, rsol INT, rtok INT,
        fee INT, creator_fee INT, fields_json TEXT, PRIMARY KEY(seq, log_index));
      CREATE INDEX IF NOT EXISTS trade_mint ON trade(mint, slot);
      CREATE TABLE IF NOT EXISTS event(seq INT, log_index INT, slot INT, name TEXT, mint TEXT, fields_json TEXT,
        PRIMARY KEY(seq, log_index));
      CREATE INDEX IF NOT EXISTS event_mint ON event(mint, name);
      CREATE TABLE IF NOT EXISTS progress(k TEXT PRIMARY KEY, v INT);
      CREATE TABLE IF NOT EXISTS event_counts(name TEXT PRIMARY KEY, n INT);
    """)
    start = (out.execute("SELECT v FROM progress WHERE k='last_seq'").fetchone() or (0,))[0]
    counts = Counter(); n_tr = 0; t0 = time.time(); last_seq = start
    q = "SELECT sequence, received_unix_nanos, raw_zlib FROM raw_frame WHERE sequence>? ORDER BY sequence"
    cur = src.execute(q, (start,))
    batch = []; ev_batch = []
    for seq, recv, z in cur:
        if limit and seq > limit: break
        try:
            d = json.loads(zlib.decompress(z))
        except Exception:
            counts["undecodable_frame"] += 1; continue
        res = (d.get("params") or {}).get("result") or {}
        val = res.get("value") or {}
        if val.get("err") is not None or not isinstance(val.get("logs"), list):
            counts["failed_or_nolog"] += 1; continue
        slot = (res.get("context") or {}).get("slot"); sig = val.get("signature")
        for li, payload in events_in(val["logs"], entries):
            ent = entries.get(payload[:8])
            if ent is None:
                counts["unknown_disc"] += 1; continue
            counts[ent[0]] += 1
            if ent[0] in ("CompleteEvent", "CompletePumpAmmMigrationEvent", "MigrateBondingCurveCreatorEvent"):
                try:
                    _, f = B9D.decode_idl_event(idl, payload)
                    ev_batch.append((seq, li, slot, ent[0], str(f.get("mint")), json.dumps(f, default=str)))
                except Exception:
                    counts["event_decode_fail"] += 1
                continue
            if ent[0] != "TradeEvent": continue
            try:
                _, f = B9D.decode_idl_event(idl, payload)
            except Exception:
                counts["trade_decode_fail"] += 1; continue
            g = lambda k: f.get(k)
            batch.append((seq, li, slot, sig, recv, str(g("mint")), int(bool(g("is_buy"))),
                          g("sol_amount"), g("token_amount"), str(g("user")), g("timestamp"),
                          g("virtual_sol_reserves"), g("virtual_token_reserves"),
                          g("real_sol_reserves"), g("real_token_reserves"),
                          g("fee"), g("creator_fee"), json.dumps(f, default=str)))
        last_seq = seq
        if len(batch) >= 5000 or (seq % 200000 == 0 and batch):
            out.executemany("INSERT OR IGNORE INTO trade VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
            n_tr += len(batch); batch = []
            out.executemany("INSERT OR IGNORE INTO event VALUES(?,?,?,?,?,?)", ev_batch); ev_batch = []
            out.execute("INSERT OR REPLACE INTO progress VALUES('last_seq',?)", (seq,)); out.commit()
            print(f"seq {seq:,}  trades {n_tr:,}  {time.time()-t0:.0f}s", flush=True)
    if batch:
        out.executemany("INSERT OR IGNORE INTO trade VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch); n_tr += len(batch)
    if ev_batch:
        out.executemany("INSERT OR IGNORE INTO event VALUES(?,?,?,?,?,?)", ev_batch)
    out.execute("INSERT OR REPLACE INTO progress VALUES('last_seq',?)", (last_seq,))
    for k, v in counts.items():
        out.execute("INSERT INTO event_counts VALUES(?,?) ON CONFLICT(name) DO UPDATE SET n=n+excluded.n", (k, v))
    out.commit()
    print("DONE", dict(counts), "trades_written", n_tr, flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
