#!/usr/bin/env python3
"""B19N — the graduated-market (PumpSwap) collector.

WHY THIS EXISTS. Window 1 captured 82 graduations and 207 post-graduation trades across them, but
49 of those 82 pools show ZERO trades despite a median observation tail of 171 hours. Two readings
fit that equally well: the pools never traded, or the capture never looked. Window 1's PumpSwap
coverage is INCIDENTAL -- it targeted bonding curves, and a trade on a graduated pool touches no
bonding curve -- so its silences carry no information. This collector replaces incidental silence
with a queried answer: it walks each pool's OWN signature history, so a pool with no trades is a
pool observed to have no trades.

WHAT MAKES IT CHEAP. PumpSwap trade events carry the full pool state -- `pool_base_token_reserves`,
`pool_quote_token_reserves` and `virtual_quote_reserves` on every Buy and Sell. Window 1 needed an
account snapshot at every observation because a bonding-curve trade event does not carry reserves;
here the price path rebuilds from the event stream alone. That removes the entire account-polling
stage, which is what made window 1 expensive. Verified on window 1's own corpus, exactly:

  * the carried reserves are PRE-trade. Chaining trade N's reserves through trade N's own amounts
    reproduces trade N+1's reserves exactly, on 30 of 61 consecutive pairs in the deepest pool; the
    31 failures are the gaps this collector exists to close, not arithmetic drift.
  * the invariant is (quote + virtual) * base, non-decreasing on 765 of 765 canonical events with
    ZERO breaks. Plain quote * base breaks on 343 of them, so the virtual term is not optional --
    though it is a per-pool CONSTANT, unchanged in 340 of 343 pools, so a simulator learns the
    offset once per pool rather than tracking it. (Earlier drafts said 787/351; those counted some
    events twice by de-duplicating on field VALUES instead of canonical coordinates.)

NOTHING HERE DECIDES ANYTHING. This is a collector. It applies no rule, ranks no cell and reports
no return. The graduated cohort it builds is an input to a study that does not exist yet, and that
study must be preregistered and frozen before this data is read for any outcome.
"""
import argparse
import collections
import hashlib
import importlib.util
import json
import os
import pathlib
import sqlite3
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Every directory this collector must never write into. Window 1 is burned and window 2 is
# mid-flight; a collector that can be pointed at either can destroy a corpus that took days.
FORBIDDEN_WORK_DIRS = ("research/b11a", "research/b11m_window2")
WORK_DIR = "research/b19n_graduated"

RPC_ENV_VAR = "SOLANA_RPC_URL"

# B19N's own marker. A populated directory WITHOUT this is somebody else's, whoever they are --
# which is what lets the guard protect corpora nobody has thought to name, including future ones.
OWNERSHIP_WITNESS = "B19N_OWNED.json"
# Every file this collector writes starts with this stem, so its own output is distinguishable
# from a stranger's without enumerating filenames that will drift as stages are added.
DATABASE_STEM = "b19n_"

# The window-1 graduation deposits, measured in LAMPORTS and not in rounded SOL. A first reading of
# these at one decimal place showed "85.0" for every pool and was written down as a protocol
# constant of exactly 85 SOL; the real spread is 53 distinct values across 5,076 lamports, and the
# constant was an artifact of formatting integers through a float for display. Recorded here as an
# observed RANGE for that reason: the substantive fact -- every graduation opens the pool at
# effectively the same size, so there is no size signal to select on -- survives, but it is a
# statement about a 0.000006% spread and not about an equality.
OBSERVED_DEPOSIT_MIN = 84_990_359_056
OBSERVED_DEPOSIT_MAX = 84_990_364_132
# A spread wider than this fraction of the deposit means the "all pools start the same size"
# observation no longer holds and any study resting on it must re-derive its population.
DEPOSIT_SPREAD_TOLERANCE_PPM = 100

TRADE_EVENTS = ("BuyEvent", "SellEvent")
POOL_EVENTS = ("CreatePoolEvent",)


class CollectionRefused(Exception):
    """Raised instead of collecting. Never caught inside this module."""


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def self_sha256():
    return hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- guards


def our_witness(directory):
    """The marker saying this directory is B19N's. Absence is what makes a directory unclaimable."""
    return pathlib.Path(directory) / OWNERSHIP_WITNESS


def foreign_content(directory):
    """Anything in `directory` that is not B19N's own output. Shape-matched, not enumerated."""
    directory = pathlib.Path(directory)
    if not directory.is_dir():
        return []
    return [child.name for child in sorted(directory.iterdir())
            if not child.name.startswith(".") and child.name != OWNERSHIP_WITNESS
            and not child.name.startswith(DATABASE_STEM)]


def assert_work_dir_is_ours(path, forbidden=FORBIDDEN_WORK_DIRS, root=None):
    """Refuse unless this directory is PROVABLY B19N's, or provably nobody's.

    Checked BEFORE mkdir, so a mistyped path cannot create anything on the way to being rejected.

    WHY THIS IS NOT A DENYLIST ANY MORE. The first version asked "is this one of two names I was
    told to avoid?" -- and the peer seat showed that is the design b11c had just abandoned, for the
    reason it abandoned it. A denylist must be hand-maintained against every precious directory in
    the repository, forever, and it was ALREADY incomplete: only window 1 and window 2 were named,
    so any other spent corpus was protected only incidentally, by sitting inside `research/`. Point
    a `--work-dir` one level deeper, at a precious directory nobody remembered to list, and it wrote
    straight in. A window 3 would have been unprotected until someone edited a tuple.

    So the question is inverted, exactly as `b11c.assert_directory_is_claimable` inverts it. A
    directory is writable only if it is EMPTY or carries B19N's own witness. That protects every
    precious directory by construction, including ones that do not exist yet and ones nobody thought
    to name -- because they all have content and none of them carry this collector's witness.

    ONE INHERENT RESIDUAL, recorded because it is the fail-closed rule working as designed and not
    a gap to be fixed: an EMPTY directory a run is legitimately pointed at cannot be protected
    retroactively if it later becomes precious. Nothing can protect it -- at the moment of the
    decision there is nothing to distinguish it from scratch space. That is true of any collector.

    The containment check is kept on top of that. It is redundant for safety but not for diagnosis:
    "this belongs to window 1" is a message an operator can act on, where "this directory is not
    empty" is one they will be tempted to work around. It is also NOT redundant for an EMPTY
    forbidden directory -- a freshly created window that has not collected yet has no content for
    the fail-closed rule to catch, so containment is the only thing standing there.

    `forbidden` and `root` are injectable for exactly that reason. Driving containment against the
    real window 1 proves nothing about the containment code, because window 1 is full and the
    fail-closed rule refuses it whatever containment does -- a peer-style mutation run confirmed
    that dropping any single containment arm left every such test green. Only an EMPTY forbidden
    directory reaches the branch, and one of those cannot be manufactured out of a real corpus.
    """
    target = pathlib.Path(path).resolve()
    base = pathlib.Path(root) if root is not None else ROOT
    for relative in forbidden:
        owned = (base / relative).resolve()
        if target == owned or owned in target.parents or target in owned.parents:
            raise CollectionRefused(
                f"REFUSING: {target} is, contains, or lies inside {owned}, which belongs to another "
                "collection. This collector writes only to its own directory. Window 1 is burned "
                "and window 2 is mid-flight; neither can be rewritten by a later run.")
    if target.exists() and not target.is_dir():
        raise CollectionRefused(f"REFUSING: {target} exists and is not a directory.")
    strangers = foreign_content(target)
    if strangers and not our_witness(target).exists():
        shown = ", ".join(strangers[:4]) + (f", and {len(strangers) - 4} more"
                                            if len(strangers) > 4 else "")
        raise CollectionRefused(
            f"REFUSING: {target} already holds content this collector did not write ({shown}) and "
            f"carries no {OWNERSHIP_WITNESS}. Fail-closed: a directory that cannot prove it is "
            "B19N's is treated as somebody else's, because the alternative is a list of precious "
            "directories that someone must remember to extend. Point this run at an empty "
            "directory, or at one B19N already owns.")
    return target


def claim_work_dir(directory):
    """Write B19N's witness, so a later run can tell its own corpus from a stranger's."""
    witness = our_witness(directory)
    if witness.exists():
        return witness
    witness.write_text(json.dumps({
        "owner": "B19N_GRADUATED_COLLECTOR",
        "collector_sha256": self_sha256(),
        "why": ("Marks this directory as B19N's own. Its absence is what makes a populated "
                "directory unclaimable, so every other corpus in the repository is protected by "
                "construction rather than by being named in a list."),
    }, indent=2, sort_keys=True) + "\n")
    return witness


def rpc_endpoint():
    url = os.environ.get(RPC_ENV_VAR)
    if not url:
        raise CollectionRefused(
            f"REFUSING: {RPC_ENV_VAR} is not set. Credentials are environment-only and are never "
            "read from a file, a flag or a committed document. Export it and re-run.")
    return url


def assert_deposit_uniform(pools, *, tolerance_ppm=DEPOSIT_SPREAD_TOLERANCE_PPM):
    """Report -- never filter -- how tightly the graduation deposits cluster. Exact integers only.

    The question this answers is not "are they equal" but "are they close enough that no study may
    select on size". Equality was the first answer and it was wrong: it came from printing lamports
    through a float at one decimal place. So the test is a SPREAD against a stated tolerance, in
    parts per million of the deposit, computed without dividing anything into a float.

    All pools are kept whatever this returns. A collector that drops what surprises it collects its
    own assumptions.
    """
    deposits = sorted(p["quote_deposit"] for p in pools if p.get("quote_deposit") is not None)
    if not deposits:
        return {"clustered": None, "reason": "no graduation carried a quote deposit"}
    low, high = deposits[0], deposits[-1]
    spread = high - low
    # Exact integer comparison: spread/low <= tol/1e6  <=>  spread * 1e6 <= low * tol
    clustered = spread * 1_000_000 <= low * tolerance_ppm
    outside_observed = [d for d in deposits if not OBSERVED_DEPOSIT_MIN <= d <= OBSERVED_DEPOSIT_MAX]
    return {
        "clustered": clustered,
        "tolerance_ppm": tolerance_ppm,
        "distinct_values": len(set(deposits)),
        "min": low, "max": high, "spread_lamports": spread,
        "spread_ppm_of_min": (spread * 1_000_000) // low,
        "outside_window_1_observed_range": len(outside_observed),
        "note": ("the deposits cluster inside the stated tolerance, so every pool opens at "
                 "effectively one size and there is no size to select on -- this is a statement "
                 "about a spread, NOT about an equality"
                 if clustered else
                 f"the deposits span {spread:,} lamports, wider than the {tolerance_ppm} ppm "
                 "tolerance. Pools do NOT all open at one size on this population and any study "
                 "that assumed they did must re-derive its population before reading a figure."),
    }


# ------------------------------------------------------------------- cohort discovery


def graduated_cohort(corpus_path, b9d=None):
    """Every pool created in a corpus, with the mint it graduated from. Read-only, no RPC.

    The cohort is derived from CreatePoolEvent rather than from a list, because a hand-kept list of
    pool addresses is one more copy of a value that will drift from the corpus that produced it.
    """
    B9D = b9d or _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")
    uri = f"file:{pathlib.Path(corpus_path).resolve()}?mode=ro&immutable=1"
    db = sqlite3.connect(uri, uri=True)
    idl = {B9D.PUMPSWAP_PROGRAM: B9D.load_pinned_idl(
        B9D.PUMPSWAP_IDL_PATH, B9D.PUMPSWAP_IDL_SHA256, B9D.PUMPSWAP_PROGRAM)}
    pools, seen = [], set()
    for signature, slot, tx_index, outer, inner in db.execute(
            "SELECT signature, slot, transaction_index, outer_index, inner_index FROM instruction "
            "WHERE program_id=? AND idl_name='event:CreatePoolEvent' "
            "ORDER BY slot, transaction_index, outer_index, inner_index",
            (B9D.PUMPSWAP_PROGRAM,)):
        row = db.execute("SELECT raw_zlib FROM raw_transaction WHERE signature=?",
                         (signature,)).fetchone()
        if row is None:
            continue
        try:
            envelopes = B9D.envelope_instructions(B9D.raw_result(row[0]))
        except Exception as error:                                            # noqa: BLE001
            raise CollectionRefused(
                f"REFUSING: {signature} carries a CreatePoolEvent row but its body will not "
                f"decode ({type(error).__name__}). A cohort built by skipping the bodies it "
                "cannot read is a cohort of the bodies that happened to parse.") from error
        for envelope in envelopes:
            if envelope.get("program_id") != B9D.PUMPSWAP_PROGRAM:
                continue
            try:
                event = B9D.decode_anchor_cpi_event(
                    B9D.PUMPSWAP_PROGRAM, envelope.get("data"), idl)
            except Exception:                                                 # noqa: BLE001
                continue
            if not event or event["name"] not in POOL_EVENTS:
                continue
            fields = event["fields"]
            pool = str(fields.get("pool"))
            key = (slot, tx_index, outer, inner, pool)
            if key in seen or pool in {p["pool"] for p in pools}:
                continue
            seen.add(key)
            pools.append({
                "pool": pool,
                "base_mint": str(fields.get("base_mint")),
                "created_slot": slot,
                "created_transaction_index": tx_index,
                "quote_deposit": fields.get("pool_quote_amount"),
                "base_deposit": fields.get("pool_base_amount"),
                "coin_creator": str(fields.get("coin_creator")),
            })
    db.close()
    pools.sort(key=lambda p: (p["created_slot"], p["created_transaction_index"], p["pool"]))
    return pools


# --------------------------------------------------------------------------- storage


SCHEMA = """
CREATE TABLE IF NOT EXISTS pool (
    pool TEXT PRIMARY KEY, base_mint TEXT, created_slot INTEGER,
    created_transaction_index INTEGER, quote_deposit INTEGER, base_deposit INTEGER,
    coin_creator TEXT, signatures_complete INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS pool_signature (
    pool TEXT, signature TEXT, slot INTEGER, err INTEGER,
    PRIMARY KEY (pool, signature));
CREATE TABLE IF NOT EXISTS raw_transaction (
    signature TEXT PRIMARY KEY, method TEXT, params_json TEXT, received_at_unix REAL,
    response_sha256 TEXT, raw_zlib BLOB);
CREATE TABLE IF NOT EXISTS raw_signature_page (
    page_key TEXT PRIMARY KEY, method TEXT, params_json TEXT, received_at_unix REAL,
    response_sha256 TEXT, raw_zlib BLOB);
CREATE TABLE IF NOT EXISTS run_meta (key TEXT PRIMARY KEY, value TEXT);
"""


def open_database(work_dir):
    target = assert_work_dir_is_ours(work_dir)
    target.mkdir(parents=True, exist_ok=True)
    claim_work_dir(target)
    database = sqlite3.connect(target / "b19n_graduated.sqlite")
    database.executescript(SCHEMA)
    return database


def record_meta(database, key, value):
    existing = database.execute("SELECT value FROM run_meta WHERE key=?", (key,)).fetchone()
    if existing and existing[0] != str(value):
        raise CollectionRefused(
            f"REFUSING: run_meta[{key}] was {existing[0]!r} and this run carries {str(value)!r}. "
            "A corpus assembled under two different configurations is not one corpus.")
    database.execute("INSERT OR REPLACE INTO run_meta (key,value) VALUES (?,?)", (key, str(value)))


# ------------------------------------------------------------------------ collection


def collect_pool_signatures(database, endpoint, pool, b9d, *, limit=1000, cap_pages=64,
                            opener=None):
    """Walk one pool's whole signature history, oldest-ward, storing every page byte-exact.

    Returns (new_signatures, pages, complete). `complete` is False only if the page cap bound the
    walk -- a truncated history is recorded as truncated and never as an empty tail, because the
    entire point of this collector is that a silence must be a queried silence.
    """
    before, pages, stored, complete = None, 0, 0, True
    while True:
        if pages >= cap_pages:
            complete = False
            break
        params = [pool, {"limit": limit}]
        if before:
            params[1]["before"] = before
        raw, result = b9d.rpc_request(endpoint, "getSignaturesForAddress", params,
                                      opener=opener)
        page_key = hashlib.sha256(
            json.dumps([pool, pages, before], separators=(",", ":")).encode()).hexdigest()
        b9d.store_raw(database, "raw_signature_page", "page_key", page_key,
                      "getSignaturesForAddress", params, raw)
        pages += 1
        if not result:
            break
        for entry in result:
            signature = entry.get("signature")
            if not signature:
                continue
            database.execute(
                "INSERT OR IGNORE INTO pool_signature (pool,signature,slot,err) VALUES (?,?,?,?)",
                (pool, signature, entry.get("slot"), 1 if entry.get("err") else 0))
            stored += 1
        before = result[-1].get("signature")
        if len(result) < limit:
            break
    database.execute("UPDATE pool SET signatures_complete=? WHERE pool=?",
                     (1 if complete else 0, pool))
    return stored, pages, complete


def collect_bodies(database, endpoint, b9d, *, opener=None, limit=None):
    """Fetch every not-yet-stored transaction body, in canonical (slot, signature) order."""
    query = ("SELECT DISTINCT s.signature, s.slot FROM pool_signature s "
             "LEFT JOIN raw_transaction r ON r.signature=s.signature "
             "WHERE r.signature IS NULL AND s.err=0 ORDER BY s.slot, s.signature")
    pending = [row for row in database.execute(query)]
    if limit is not None:
        pending = pending[:limit]
    fetched = 0
    for signature, _slot in pending:
        params = [signature, {"encoding": "json", "maxSupportedTransactionVersion": 0,
                              "commitment": "finalized"}]
        raw, _result = b9d.rpc_request(endpoint, "getTransaction", params, opener=opener)
        b9d.store_raw(database, "raw_transaction", "signature", signature,
                      "getTransaction", params, raw)
        fetched += 1
        if fetched % 200 == 0:
            database.commit()
    database.commit()
    return fetched, len(pending)


# --------------------------------------------------------------------------- stages


def stage_cohort(args, b9d):
    pools = graduated_cohort(args.source_corpus, b9d=b9d)
    if not pools:
        raise CollectionRefused(
            f"REFUSING: {args.source_corpus} yielded no CreatePoolEvent. A graduated cohort of "
            "zero is not a cohort; check that the corpus is the one that observed the window.")
    database = open_database(args.work_dir)
    record_meta(database, "source_corpus", pathlib.Path(args.source_corpus).resolve())
    record_meta(database, "collector_sha256", self_sha256())
    for pool in pools:
        database.execute(
            "INSERT OR IGNORE INTO pool (pool,base_mint,created_slot,created_transaction_index,"
            "quote_deposit,base_deposit,coin_creator) VALUES (?,?,?,?,?,?,?)",
            (pool["pool"], pool["base_mint"], pool["created_slot"],
             pool["created_transaction_index"], pool["quote_deposit"], pool["base_deposit"],
             pool["coin_creator"]))
    database.commit()
    census = {
        "pools": len(pools),
        "slot_span": [pools[0]["created_slot"], pools[-1]["created_slot"]],
        "distinct_creators": len({p["coin_creator"] for p in pools}),
        "deposit_uniformity": assert_deposit_uniform(pools),
    }
    database.close()
    return census


def stage_signatures(args, b9d):
    endpoint = rpc_endpoint()
    database = open_database(args.work_dir)
    pools = [row[0] for row in database.execute(
        "SELECT pool FROM pool WHERE signatures_complete=0 ORDER BY created_slot, pool")]
    walked, truncated, total = 0, [], 0
    for pool in pools:
        stored, _pages, complete = collect_pool_signatures(database, endpoint, pool, b9d)
        total += stored
        walked += 1
        if not complete:
            truncated.append(pool)
        database.commit()
    remaining = database.execute(
        "SELECT COUNT(*) FROM pool WHERE signatures_complete=0").fetchone()[0]
    database.close()
    return {"pools_walked": walked, "signatures_recorded": total,
            "pools_truncated_by_page_cap": len(truncated), "pools_still_pending": remaining}


def stage_bodies(args, b9d):
    endpoint = rpc_endpoint()
    database = open_database(args.work_dir)
    fetched, pending = collect_bodies(database, endpoint, b9d, limit=args.max_bodies)
    stored = database.execute("SELECT COUNT(*) FROM raw_transaction").fetchone()[0]
    database.close()
    return {"bodies_fetched_this_run": fetched, "bodies_pending_at_start": pending,
            "bodies_stored_total": stored}


def stage_census(args, b9d):
    """What is here, with silence separated from absence. No RPC, no writes."""
    database = open_database(args.work_dir)
    pools = database.execute(
        "SELECT pool, created_slot, signatures_complete FROM pool ORDER BY created_slot").fetchall()
    counts = dict(database.execute(
        "SELECT pool, COUNT(*) FROM pool_signature GROUP BY pool").fetchall())
    bodies = database.execute("SELECT COUNT(*) FROM raw_transaction").fetchone()[0]
    observed_zero = [p for p, _s, complete in pools if complete and counts.get(p, 0) == 0]
    unqueried = [p for p, _s, complete in pools if not complete]
    depths = sorted((counts.get(p, 0) for p, _s, complete in pools if complete), reverse=True)
    database.close()
    return {
        "pools": len(pools),
        "bodies_stored": bodies,
        "pools_fully_walked": len(pools) - len(unqueried),
        "pools_observed_to_have_no_activity": len(observed_zero),
        "pools_not_yet_walked": len(unqueried),
        "depth_top": depths[:12],
        "depth_median": depths[(len(depths) - 1) // 2] if depths else None,
        "reading": ("pools_observed_to_have_no_activity is a MEASURED silence -- the pool's own "
                    "signature history was walked to its end and held nothing. It is not the same "
                    "quantity as window 1's 49 empty pools, which were never queried at all."),
    }


STAGES = {"cohort": stage_cohort, "signatures": stage_signatures,
          "bodies": stage_bodies, "census": stage_census}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("stage", nargs="?", choices=sorted(STAGES),
                        help="cohort -> signatures -> bodies -> census")
    parser.add_argument("--source-corpus", default=str(ROOT / "research/b11a/b11a_bodies.sqlite"),
                        help="corpus the graduated cohort is derived from (read-only)")
    parser.add_argument("--work-dir", default=str(ROOT / WORK_DIR))
    parser.add_argument("--max-bodies", type=int, default=None)
    parser.add_argument("--self-hash", action="store_true")
    args = parser.parse_args(argv)
    if args.self_hash:
        print(self_sha256())
        return 0
    if not args.stage:
        parser.error("a stage is required unless --self-hash is given")
    b9d = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")
    try:
        report = STAGES[args.stage](args, b9d)
    except CollectionRefused as refusal:
        print(str(refusal), file=sys.stderr)
        return 2
    print(json.dumps({"stage": args.stage, "collector_sha256": self_sha256(),
                      "report": report}, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
