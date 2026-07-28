#!/usr/bin/env python3
"""B7j - graduation-anchor positive control, frozen by
research/B7J_POSITIVE_CONTROL_PREREGISTRATION.md.

Two independent paths over the frozen 439-slot envelope:
  reference  - every retrievable block, decoded for the two frozen graduation events
               (PUBLIC endpoint, the one B7h used)
  candidate  - each distinct reference bonding_curve's address history
               (CREDENTIALED endpoint, the one B7e used)

Endpoints are pinned per path. There is NO silent provider fallback: collapsing both paths onto
one provider would destroy the cross-provider independence the test depends on, so an unavailable
or throttled path fails visibly instead.

Read-only. No signing, no spending, no deployment, no live or devnet transactions.
Credentials are read from the environment and never printed or persisted.
"""
import argparse
import base64
import concurrent.futures as cf
import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
import zlib

try:
    import b7d_create_enumerator as b7d
except ModuleNotFoundError:
    from scripts import b7d_create_enumerator as b7d

# Frozen by the preregistration. S = 435565104, W = 220 -> [S-219, S+220).
WINDOW_START = 435564885
WINDOW_END = 435565324
EVENT_NAMES = ("CompleteEvent", "CompletePumpAmmMigrationEvent")
PUBLIC_RPC = "https://api.mainnet-beta.solana.com"
RATE_LIMIT_PREFIX = "RATE_LIMIT"


class PathUnavailable(RuntimeError):
    """A pinned path is throttled or unreachable. Never fall back to the other provider."""


def event_discriminators():
    return {hashlib.sha256(f"event:{n}".encode()).digest()[:8]: n for n in EVENT_NAMES}


def rpc(url, method, params, retries=4, timeout=90):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = json.loads(response.read())
            if "error" in payload:
                code = payload["error"].get("code")
                message = str(payload["error"].get("message") or "")
                # Throttling can arrive as a JSON-RPC error body rather than an HTTP status.
                # Treating it as an ordinary error would let a throttled path masquerade as a
                # clean negative result, so it is classified as unavailable here too.
                if code in (429, 403, -32429, -32005) or "rate limit" in message.lower() \
                        or "too many requests" in message.lower():
                    raise PathUnavailable(f"{RATE_LIMIT_PREFIX} rpc {code}: {message[:80]}")
                return None, f"{code}: {message}"
            return payload.get("result"), None
        except PathUnavailable:
            raise                     # never downgraded by the broad handler below
        except urllib.error.HTTPError as error:
            if error.code in (403, 429):
                # Pinned path is throttled. Fail visibly rather than switching providers.
                raise PathUnavailable(f"{RATE_LIMIT_PREFIX} HTTP {error.code}") from None
            last = f"HTTPError {error.code}"
        except Exception as error:  # noqa: BLE001
            last = f"{type(error).__name__}"
        if attempt + 1 < retries:
            time.sleep(min(0.5 * 2 ** attempt, 8))
    return None, last or "unknown rpc failure"


def decode_events(raw_json, discs, types, source_slot=None, source_tx_index=None):
    """Decode the two frozen events from one transaction. Returns (rows, errors).

    Rows carry the full canonical key. `event_ordinal` is assigned in decode order within each
    (signature, outer, inner) group and is never defaulted.
    """
    rows, errors = [], []
    meta = raw_json.get("meta") or {}
    if meta.get("err") is not None:
        return rows, errors
    signature = raw_json["transaction"]["signatures"][0]
    slot = raw_json.get("slot", source_slot)
    ordinals = {}
    for group in meta.get("innerInstructions") or []:
        outer = group["index"]
        for inner, instruction in enumerate(group.get("instructions", [])):
            if instruction.get("programId") != b7d.PUMP or not instruction.get("data"):
                continue
            encoded = b7d.b58decode(instruction["data"])
            if len(encoded) < 16 or encoded[:8] != b7d.EVENT_TAG:
                continue
            name = discs.get(encoded[8:16])
            if name is None:
                continue          # out of scope by the frozen rule; skipped silently
            payload = encoded[8:]
            key = (signature, outer, inner)
            ordinal = ordinals.get(key, 0)
            ordinals[key] = ordinal + 1
            try:
                cursor = b7d.Cursor(payload[8:])
                fields = b7d.read_struct(cursor, types[name], types)
                if cursor.remaining:
                    raise ValueError(f"{cursor.remaining} trailing bytes")
            except Exception as error:  # noqa: BLE001
                errors.append((slot, signature, outer, inner, name,
                               f"{type(error).__name__}: {error}"))
                continue
            rows.append({
                "slot": slot, "transaction_index": source_tx_index, "signature": signature,
                "outer_instruction_index": outer, "inner_instruction_index": inner,
                "event_ordinal": ordinal, "event_name": name, "mint": fields["mint"],
                "bonding_curve": fields.get("bonding_curve"),
                "event_payload_base64": base64.b64encode(payload).decode(),
            })
    return rows, errors


def canonical_key(row):
    return (row["slot"], row["transaction_index"], row["signature"],
            row["outer_instruction_index"], row["inner_instruction_index"],
            row["event_ordinal"], row["mint"], row["event_payload_base64"])


def connect(path):
    db = sqlite3.connect(path)
    db.executescript("""
        PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS slot_scan(
          slot INTEGER PRIMARY KEY, status TEXT NOT NULL, error TEXT, scanned_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS event_row(
          side TEXT NOT NULL, slot INTEGER, transaction_index INTEGER, signature TEXT NOT NULL,
          outer_instruction_index INTEGER NOT NULL, inner_instruction_index INTEGER NOT NULL,
          event_ordinal INTEGER NOT NULL, event_name TEXT NOT NULL, mint TEXT NOT NULL,
          bonding_curve TEXT, event_payload_base64 TEXT NOT NULL,
          PRIMARY KEY(side, signature, outer_instruction_index, inner_instruction_index,
                      event_ordinal));
        CREATE TABLE IF NOT EXISTS raw_payload(
          side TEXT NOT NULL, signature TEXT NOT NULL, slot INTEGER,
          raw_zlib BLOB NOT NULL, PRIMARY KEY(side, signature));
        CREATE TABLE IF NOT EXISTS run_error(
          stage TEXT NOT NULL, detail TEXT NOT NULL, at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS raw_block(
          slot INTEGER PRIMARY KEY, raw_zlib BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS raw_history_page(
          bonding_curve TEXT NOT NULL, page_index INTEGER NOT NULL, raw_zlib BLOB NOT NULL,
          PRIMARY KEY(bonding_curve, page_index));
        CREATE TABLE IF NOT EXISTS curve_history(
          bonding_curve TEXT PRIMARY KEY, pages INTEGER NOT NULL, signatures INTEGER NOT NULL,
          boundary_proven INTEGER NOT NULL);
    """)
    return db


def record_error(db, stage, detail):
    db.execute("INSERT INTO run_error VALUES (?,?,?)", (stage, str(detail)[:500], time.time()))
    db.commit()


def event_row_values(side, row):
    """One place that fixes the column order for both paths, so they cannot drift apart."""
    return (side, row["slot"], row["transaction_index"], row["signature"],
            row["outer_instruction_index"], row["inner_instruction_index"],
            row["event_ordinal"], row["event_name"], row["mint"],
            row["bonding_curve"], row["event_payload_base64"])


EVENT_ROW_INSERT = "INSERT OR REPLACE INTO event_row VALUES (?,?,?,?,?,?,?,?,?,?,?)"

# Everything a rerun would have to discard. metadata/slot_scan are handled separately because
# they are reset, not emptied.
RESETTABLE_TABLES = ("event_row", "run_error", "raw_payload", "raw_block",
                     "raw_history_page", "curve_history")


def record_candidate_rows(db, rows, mints, candidate):
    """Filter to reference mints, dedupe on the canonical key, and persist in the same
    transaction as the raw payload the rows came from.

    These rows used to be written in one batch after the whole candidate loop finished, so any
    crash or fetch failure left a database whose `raw_payload` proved the transactions had been
    examined while `event_row` held zero candidate rows - indistinguishable from "we looked and
    found nothing". The reference path already committed per slot; this gives the candidate path
    the same durability.
    """
    for row in rows:
        if row["mint"] not in mints:
            continue
        row["transaction_index"] = None
        candidate[canonical_key(row)] = row
        db.execute(EVENT_ROW_INSERT, event_row_values("candidate", row))


def completed_summary(db):
    """The summary row is written only after a run reaches a verdict; its presence means the
    database is a finished artifact rather than a work area."""
    row = db.execute("SELECT value FROM metadata WHERE key='summary'").fetchone()
    return row[0] if row else None


def has_prior_data(db):
    for table in RESETTABLE_TABLES:
        if db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
            return True
    if completed_summary(db) is not None:
        return True
    return bool(db.execute(
        "SELECT 1 FROM slot_scan WHERE status!='pending' LIMIT 1").fetchone())


def reset_for_rerun(db):
    """Clear every derived, raw and history table and return all slots to pending.

    Every run rescans all 439 slots, so retained partial state from an earlier run would let it
    contaminate this run's verdict. The clearing itself is correct; see `guard_rerun` for why it
    must never happen implicitly.
    """
    for table in RESETTABLE_TABLES:
        db.execute(f"DELETE FROM {table}")
    db.execute("DELETE FROM metadata WHERE key='summary'")
    db.execute("UPDATE slot_scan SET status='pending', error=NULL, scanned_at=?", (time.time(),))
    db.commit()


def guard_rerun(db, database, reset):
    """Fail closed before a rerun can destroy evidence.

    The defect this fixes: an ordinary re-invocation of the same command line silently deleted
    every raw block, raw transaction and history page held by the database. Those are
    irreplaceable primary evidence - the audit trail a PASS verdict rests on - not derived state
    that can be recomputed. The clear was right; doing it implicitly was not.

    Two guards, both fail-closed:
      * a database holding *any* prior data requires an explicit `--reset`;
      * a database holding a *completed* run refuses `--reset` outright. A finished artifact is
        moved aside by hand or a new `--database` path is used; no flag may overwrite it.
    """
    if not has_prior_data(db):
        return
    summary = completed_summary(db)
    if summary is not None:
        raise SystemExit(
            f"{database} holds a COMPLETED run (metadata.summary is present). Refusing to "
            f"destroy it. Point --database at a new path, or move this file aside first; "
            f"--reset is deliberately not honoured for a finished artifact.")
    if not reset:
        raise SystemExit(
            f"{database} already contains data from an earlier run. Every run rescans all "
            f"{WINDOW_END - WINDOW_START} slots, so that data cannot be kept - but clearing it "
            f"deletes raw blocks, transactions and history pages that cannot be re-derived. "
            f"Re-run with --reset to discard them deliberately, or use a new --database path.")
    reset_for_rerun(db)


def paginate_curve(url, address, window_start, db, max_pages=40):
    """Page backwards until a page PROVES it crossed below window_start.

    A cap, an ambiguous boundary, or any fetch failure fails visibly - never treated as
    'history exhausted'.
    """
    out, before, pages, proven = [], None, 0, False
    while pages < max_pages:
        params = {"limit": 1000, "commitment": "finalized"}
        if before:
            params["before"] = before
        result, error = rpc(url, "getSignaturesForAddress", [address, params])
        if error:
            raise RuntimeError(f"history fetch failed for {address}: {error}")
        # Persist the page itself: counts in curve_history cannot reproduce discovery.
        db.execute("INSERT OR REPLACE INTO raw_history_page VALUES (?,?,?)",
                   (address, pages, zlib.compress(
                       json.dumps(result, separators=(",", ":")).encode())))
        pages += 1
        if not result:
            proven = True          # empty page: nothing older exists
            break
        out.extend(result)
        oldest = min(r["slot"] for r in result)
        if oldest < window_start:
            proven = True
            break
        before = result[-1]["signature"]
    db.execute("INSERT OR REPLACE INTO curve_history VALUES (?,?,?,?)",
               (address, pages, len(out), int(proven)))
    db.commit()
    if not proven:
        raise RuntimeError(
            f"pagination cap {max_pages} reached for {address} without proving the window "
            f"boundary; refusing to treat as exhausted")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--idl", default="research/pump_idl_9c82f61.json")
    parser.add_argument("--candidate-rpc-env", default="SOLANA_RPC_URL")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--reset", action="store_true",
                        help="discard all data from an earlier run in --database. Required "
                             "before any rerun, and never honoured for a database holding a "
                             "completed run.")
    args = parser.parse_args()

    raw_idl = open(args.idl, "rb").read()
    types = {item["name"]: item for item in json.loads(raw_idl)["types"]}
    discs = event_discriminators()
    idl_hash = hashlib.sha256(raw_idl).hexdigest()

    candidate_url = os.environ.get(args.candidate_rpc_env)
    if not candidate_url:
        raise SystemExit(f"{args.candidate_rpc_env} not set; candidate path is pinned to the "
                         f"credentialed endpoint and must not fall back")

    db = connect(args.database)
    expected = {"window_start": str(WINDOW_START), "window_end": str(WINDOW_END),
                "idl_sha256": idl_hash, "event_set": ",".join(sorted(EVENT_NAMES)),
                "reference_endpoint_ref": "public-mainnet",
                "candidate_endpoint_ref": "configured-mainnet"}
    present = {k: v for k, v in db.execute("SELECT key,value FROM metadata") if k != "summary"}
    if present and present != expected:
        # Reusing a database built under different parameters would silently mix incomparable
        # runs. Refuse rather than INSERT OR REPLACE over it.
        raise SystemExit(f"database metadata mismatch; refusing to reuse {args.database}")
    if not present:
        db.executemany("INSERT INTO metadata VALUES (?,?)", expected.items())
    # Deterministic rerun, but never an implicit one: guard_rerun refuses outright if the
    # database holds a completed run, and otherwise demands --reset before clearing anything.
    guard_rerun(db, args.database, args.reset)
    db.executemany("INSERT OR IGNORE INTO slot_scan VALUES (?,'pending',NULL,?)",
                   ((s, time.time()) for s in range(WINDOW_START, WINDOW_END)))
    db.commit()

    # ---------------- reference path: PUBLIC endpoint ----------------
    print(f"reference path: {WINDOW_END - WINDOW_START} slots, public endpoint", flush=True)
    reference = []

    def fetch_block(slot):
        return slot, rpc(PUBLIC_RPC, "getBlock", [slot, {
            "encoding": "jsonParsed", "transactionDetails": "full", "rewards": False,
            "maxSupportedTransactionVersion": 0}])

    try:
        with cf.ThreadPoolExecutor(max_workers=args.workers) as executor:
            for slot, (block, error) in executor.map(fetch_block,
                                                     range(WINDOW_START, WINDOW_END)):
                if error and ("-32007" in error or "-32009" in error):
                    db.execute("UPDATE slot_scan SET status='skipped',error=?,scanned_at=? "
                               "WHERE slot=?", (error, time.time(), slot))
                    db.commit()
                    continue
                if error or block is None:
                    db.execute("UPDATE slot_scan SET status='error',error=?,scanned_at=? "
                               "WHERE slot=?", (error or "null block", time.time(), slot))
                    db.commit()
                    record_error(db, "reference_block", f"slot {slot}: {error}")
                    continue
                # Persist the whole retrieved block so reference COMPLETENESS is auditable,
                # not merely the transactions that happened to decode an event.
                db.execute("INSERT OR REPLACE INTO raw_block VALUES (?,?)",
                           (slot, zlib.compress(json.dumps(block,
                                                           separators=(",", ":")).encode())))
                for tx_index, transaction in enumerate(block.get("transactions", [])):
                    rows, errors = decode_events(transaction, discs, types, slot, tx_index)
                    for err in errors:
                        record_error(db, "reference_decode", str(err))
                    for row in rows:
                        reference.append(row)
                        db.execute(EVENT_ROW_INSERT, event_row_values("reference", row))
                        db.execute("INSERT OR REPLACE INTO raw_payload VALUES ('reference',?,?,?)",
                                   (row["signature"], slot,
                                    zlib.compress(json.dumps(transaction,
                                                             separators=(",", ":")).encode())))
                db.execute("UPDATE slot_scan SET status='retrieved',error=NULL,scanned_at=? "
                           "WHERE slot=?", (time.time(), slot))
                db.commit()
    except PathUnavailable as error:
        record_error(db, "reference_path_unavailable", error)
        print(json.dumps({"result": "FAIL", "reason": f"reference path unavailable: {error}",
                          "note": "no provider fallback permitted"}), flush=True)
        return 2

    # reconcile skips independently
    produced, error = rpc(PUBLIC_RPC, "getBlocks", [WINDOW_START, WINDOW_END - 1])
    if error or produced is None:
        record_error(db, "getBlocks", error or "null getBlocks result")
    else:
        produced = set(produced)
        for slot, status in db.execute(
                "SELECT slot,status FROM slot_scan WHERE status='skipped'").fetchall():
            if slot in produced:
                # getBlock called it skipped but the ledger says it was produced: unexplained.
                db.execute("UPDATE slot_scan SET status='error',error=?,scanned_at=? WHERE slot=?",
                           ("skipped by getBlock but present in getBlocks", time.time(), slot))
            else:
                db.execute("UPDATE slot_scan SET status='verified_skipped',scanned_at=? "
                           "WHERE slot=?", (time.time(), slot))
        db.commit()

    ref_types = sorted({r["event_name"] for r in reference})
    print(f"reference events: {len(reference)}  types: {ref_types}", flush=True)

    # ---------------- candidate path: CREDENTIALED endpoint ----------------
    curves = sorted({r["bonding_curve"] for r in reference if r.get("bonding_curve")})
    mints = {r["mint"] for r in reference}
    print(f"candidate path: {len(curves)} distinct bonding curves, credentialed endpoint",
          flush=True)
    candidate = {}
    try:
        for address in curves:
            history = paginate_curve(candidate_url, address, WINDOW_START, db)
            for entry in history:
                if not (WINDOW_START <= entry["slot"] < WINDOW_END):
                    continue
                transaction, error = rpc(candidate_url, "getTransaction",
                                         [entry["signature"],
                                          {"encoding": "jsonParsed",
                                           "maxSupportedTransactionVersion": 0,
                                           "commitment": "finalized"}])
                if error or transaction is None:
                    raise RuntimeError(f"candidate tx fetch failed {entry['signature']}: {error}")
                # Persist every in-window candidate transaction examined, including those that
                # decode zero frozen events - otherwise "we looked and found nothing" is not
                # auditable.
                db.execute("INSERT OR REPLACE INTO raw_payload VALUES ('candidate',?,?,?)",
                           (entry["signature"], entry["slot"],
                            zlib.compress(json.dumps(transaction,
                                                     separators=(",", ":")).encode())))
                tx_index = None
                rows, errors = decode_events(transaction, discs, types, entry["slot"], tx_index)
                for err in errors:
                    record_error(db, "candidate_decode", str(err))
                record_candidate_rows(db, rows, mints, candidate)
                db.commit()
    except PathUnavailable as error:
        record_error(db, "candidate_path_unavailable", error)
        print(json.dumps({"result": "FAIL", "reason": f"candidate path unavailable: {error}",
                          "note": "no provider fallback permitted"}), flush=True)
        return 2
    except RuntimeError as error:
        record_error(db, "candidate", error)
        print(json.dumps({"result": "FAIL", "reason": str(error)}), flush=True)
        return 2

    # ---------------- comparison ----------------
    # FROZEN AMENDMENT (see preregistration "Canonical key amendment"): `transaction_index` is
    # NOT available from getTransaction on the candidate path, so it is excluded from the equality
    # projection by explicit rule rather than silently dropped. It is still recorded on the
    # reference side for canonical ordering and is reported in the summary.
    def projection(row):
        return (row["slot"], row["signature"], row["outer_instruction_index"],
                row["inner_instruction_index"], row["event_ordinal"], row["mint"],
                row["event_payload_base64"])

    ref_set = {projection(r) for r in reference}
    cand_set = {projection(r) for r in candidate.values()}
    missing = ref_set - cand_set
    extra = cand_set - ref_set
    bad_slots = dict(db.execute("SELECT status,COUNT(*) FROM slot_scan WHERE status NOT IN "
                                "('retrieved','verified_skipped') GROUP BY status"))
    errors = db.execute("SELECT COUNT(*) FROM run_error").fetchone()[0]
    have_both = set(EVENT_NAMES) <= {r["event_name"] for r in reference}

    if not have_both:
        verdict = "INCONCLUSIVE"
    elif missing or extra or bad_slots or errors:
        verdict = "FAIL"
    else:
        verdict = "PASS"

    summary = {"result": verdict, "window": [WINDOW_START, WINDOW_END],
               "reference_events": len(ref_set), "candidate_events": len(cand_set),
               "missing_from_candidate": len(missing), "extra_in_candidate": len(extra),
               "reference_event_types": ref_types, "both_types_present": have_both,
               "unresolved_slots": bad_slots, "run_errors": errors,
               "distinct_bonding_curves": len(curves)}
    print(json.dumps(summary, sort_keys=True), flush=True)
    db.execute("INSERT OR REPLACE INTO metadata VALUES ('summary',?)",
               (json.dumps(summary, sort_keys=True),))
    db.commit()
    db.close()
    return 0 if verdict == "PASS" else (1 if verdict == "FAIL" else 3)


if __name__ == "__main__":
    raise SystemExit(main())
