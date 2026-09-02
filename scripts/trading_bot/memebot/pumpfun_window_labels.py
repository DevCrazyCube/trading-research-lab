#!/usr/bin/env python3
"""pump.fun window labeler: read the on-chain BondingCurve `complete` flag for every
create in the b11a 23-hour enumerated window, so creator provenance can be tested with
a STRICT chronological order (create slots are known exactly here, unlike LaunchLab).

Facts established by this file's own `probe`/`validate` steps (never assumed):
  - BondingCurve discriminator = [23,183,248,55,96,216,172,96] (from research/pump_idl_9c82f61.json)
  - layout: 8 disc + virtual_token u64 + virtual_quote u64 + real_token u64 + real_quote u64
    + token_total_supply u64  => `complete` (bool) at byte offset 48, creator pubkey at 49..81
  - live accounts appear at BOTH 115 and 151 bytes; size is NOT a label, only the offset is.

Subcommands:
  probe     print schema + one sample create row, and dump a few decoded live accounts
  validate  confusion matrix of offset-48 flag vs the 82 known-graduated / N known-not
            curves in b11a_paths.sqlite
  label     bulk getMultipleAccounts over all creates, resumable, into window_labels.sqlite
  report    real counts: labels, graduation rate, creator distribution, testable cohort

PAPER-ONLY research. Free public RPC only; polite ~3 req/s.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import sqlite3
import struct
import sys
import time
import urllib.error
import urllib.request
from typing import Iterable, Sequence

RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
BC_DISCRIMINATOR = bytes([23, 183, 248, 55, 96, 216, 172, 96])

# byte offsets inside the BondingCurve account data (validated, see module docstring)
OFF_COMPLETE = 48
OFF_CREATOR = 49
OFF_MAYHEM = 81
OFF_CASHBACK = 82
SLICE_LEN = 83  # disc + 5*u64 + complete + creator + mayhem + cashback

B11A_DIR = "/home/anont/meme/research/b11a"
CREATES_DB = os.path.join(B11A_DIR, "b11a_creates.sqlite")
IDENTITY_DB = os.path.join(B11A_DIR, "b11a_identity.sqlite")
PATHS_DB = os.path.join(B11A_DIR, "b11a_paths.sqlite")
LABELS_DB = os.path.join(B11A_DIR, "window_labels.sqlite")

BATCH = 100
SLEEP_S = 0.34  # ~3 req/s
MAX_RETRIES = 8

B58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = bytearray()
    while n > 0:
        n, r = divmod(n, 58)
        out.append(B58_ALPHABET[r])
    for b in raw:
        if b == 0:
            out.append(B58_ALPHABET[0])
        else:
            break
    return bytes(reversed(out)).decode()


# --------------------------------------------------------------------------- RPC


class RpcError(RuntimeError):
    pass


def rpc(method: str, params, timeout: int = 45):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(
                RPC_URL, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as fh:
                payload = json.load(fh)
            if "error" in payload:
                last = RpcError(f"{method}: {payload['error']}")
                code = (payload["error"] or {}).get("code")
                if code == -32602:  # bad request, retrying will not help
                    raise last
            else:
                return payload["result"]
        except urllib.error.HTTPError as exc:  # 429 / 5xx
            last = exc
        except Exception as exc:  # noqa: BLE001 - network flake
            last = exc
        time.sleep(min(30.0, (2 ** attempt) * 0.5) + random.random() * 0.4)
    raise RpcError(f"{method} failed after {MAX_RETRIES} attempts: {last}")


def fetch_accounts(pubkeys: Sequence[str]) -> list[dict | None]:
    """getMultipleAccounts with a dataSlice covering the label bytes."""
    res = rpc(
        "getMultipleAccounts",
        [
            list(pubkeys),
            {
                "encoding": "base64",
                "commitment": "finalized",
                "dataSlice": {"offset": 0, "length": SLICE_LEN},
            },
        ],
    )
    return res["value"]


def decode_account(entry: dict | None) -> dict:
    """Return an explicit label record. Missing / foreign / undecodable are their OWN
    categories - a missing account is NEVER silently 'not graduated'."""
    if entry is None:
        return {"status": "missing", "complete": None}
    owner = entry.get("owner")
    if owner != PUMP_PROGRAM:
        return {"status": "foreign_owner", "complete": None, "owner": owner}
    data_field = entry.get("data") or ["", ""]
    raw = base64.b64decode(data_field[0]) if data_field[0] else b""
    if len(raw) < SLICE_LEN:
        return {"status": "short_data", "complete": None, "data_len": len(raw)}
    if raw[:8] != BC_DISCRIMINATOR:
        return {"status": "bad_discriminator", "complete": None}
    vt, vq, rt, rq, tts = struct.unpack_from("<5Q", raw, 8)
    flag = raw[OFF_COMPLETE]
    if flag not in (0, 1):
        return {"status": "bad_bool", "complete": None, "raw_flag": flag}
    return {
        "status": "ok",
        "complete": int(flag),
        "creator_onchain": b58encode(raw[OFF_CREATOR : OFF_CREATOR + 32]),
        "virtual_token_reserves": vt,
        "virtual_quote_reserves": vq,
        "real_token_reserves": rt,
        "real_quote_reserves": rq,
        "token_total_supply": tts,
        "is_mayhem_mode": raw[OFF_MAYHEM],
        "is_cashback_coin": raw[OFF_CASHBACK],
        "lamports": entry.get("lamports"),
        "data_len": entry.get("space"),
    }


def batched(seq: Sequence, n: int) -> Iterable[Sequence]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


# ------------------------------------------------------------------------- probe


def cmd_probe(_args) -> int:
    con = sqlite3.connect(f"file:{CREATES_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    print("=== create_event schema ===")
    for (sql,) in con.execute(
        "select sql from sqlite_master where type='table' and name='create_event'"
    ):
        print(sql)
    row = con.execute("select * from create_event order by slot, transaction_index limit 1").fetchone()
    print("\n=== sample create_event row ===")
    for k in row.keys():
        v = row[k]
        if isinstance(v, str) and len(v) > 160:
            v = v[:160] + f"... [{len(row[k])} chars]"
        print(f"  {k}: {v}")
    n, mints, curves, creators, bt = con.execute(
        "select count(*), count(distinct mint), count(distinct bonding_curve),"
        " count(distinct creator), count(block_time) from create_event"
    ).fetchone()
    print(
        f"\ncreate_event rows={n} distinct_mint={mints} distinct_bonding_curve={curves} "
        f"distinct_creator={creators} rows_with_block_time={bt}"
    )
    print("bonding_curve is stored per create -> no PDA derivation needed.")

    # cross-check against the decoded identity subsample
    con.execute("ATTACH ? AS idt", (IDENTITY_DB,))
    tot = con.execute("select count(*) from idt.identity").fetchone()[0]
    match = con.execute(
        "select count(*) from idt.identity i join create_event c"
        " on c.bonding_curve=i.bonding_curve and c.mint=i.mint and c.creator=i.creator"
    ).fetchone()[0]
    print(
        f"identity cross-check: {match}/{tot} = {100.0*match/tot:.4f}% of known "
        "(bonding_curve, mint, creator) triples reproduced exactly from create_event"
    )
    con.close()

    print("\n=== live account decode sample ===")
    pc = sqlite3.connect(f"file:{PATHS_DB}?mode=ro", uri=True)
    grad = [r[0] for r in pc.execute(
        "select bonding_curve from curve where complete_slot is not null limit 3")]
    nong = [r[0] for r in pc.execute(
        "select bonding_curve from curve where complete_slot is null limit 3")]
    pc.close()
    keys = grad + nong
    vals = fetch_accounts(keys)
    for k, v, tag in zip(keys, vals, ["known_grad"] * len(grad) + ["known_not"] * len(nong)):
        d = decode_account(v)
        print(f"  {tag} {k} status={d['status']} complete={d['complete']} "
              f"virt_tok={d.get('virtual_token_reserves')} space={d.get('data_len')}")
    return 0


# ---------------------------------------------------------------------- validate


def cmd_validate(args) -> int:
    pc = sqlite3.connect(f"file:{PATHS_DB}?mode=ro", uri=True)
    grad = [r[0] for r in pc.execute(
        "select bonding_curve from curve where complete_slot is not null order by bonding_curve")]
    nong_all = [r[0] for r in pc.execute(
        "select bonding_curve from curve where complete_slot is null order by bonding_curve")]
    pc.close()
    rnd = random.Random(20260902)
    nong = rnd.sample(nong_all, min(args.negatives, len(nong_all)))
    print(f"known-graduated (complete_slot NOT NULL) n={len(grad)}")
    print(f"known-not-graduated pool n={len(nong_all)}, sampled n={len(nong)} (seed 20260902)")
    print(f"NOTE window ended 2026-07-28; accounts are read TODAY, so a 'known-not' curve "
          f"that graduated AFTER the window is a true late graduation, not an offset error.")

    keys = grad + nong
    truth = {k: 1 for k in grad}
    truth.update({k: 0 for k in nong})
    decoded: dict[str, dict] = {}
    for i, chunk in enumerate(batched(keys, BATCH)):
        vals = fetch_accounts(chunk)
        for k, v in zip(chunk, vals):
            decoded[k] = decode_account(v)
        print(f"  batch {i+1}: fetched {len(chunk)} (total {len(decoded)}/{len(keys)})", flush=True)
        time.sleep(SLEEP_S)

    tp = fp = tn = fn = 0
    bad = {}
    late_evidence = []
    for k in keys:
        d = decoded[k]
        if d["status"] != "ok":
            bad[d["status"]] = bad.get(d["status"], 0) + 1
            continue
        t, p = truth[k], d["complete"]
        if t == 1 and p == 1:
            tp += 1
        elif t == 1 and p == 0:
            fn += 1
        elif t == 0 and p == 1:
            fp += 1
            late_evidence.append((k, d["virtual_token_reserves"], d["real_token_reserves"]))
        else:
            tn += 1

    print("\n=== confusion matrix, offset-48 flag vs b11a_paths in-window labels ===")
    print(f"  TP (known grad, flag=1) = {tp}")
    print(f"  FN (known grad, flag=0) = {fn}")
    print(f"  FP (known not,  flag=1) = {fp}   <- includes post-window graduations")
    print(f"  TN (known not,  flag=0) = {tn}")
    print(f"  non-ok statuses: {bad if bad else 'none'}")
    recall = tp / max(1, tp + fn)
    print(f"  recall on the 82 = {tp}/{tp+fn} = {100*recall:.2f}%")

    # structural cross-check: a graduated curve should have its reserves zeroed
    z_grad = sum(1 for k in grad if decoded[k]["status"] == "ok"
                 and decoded[k]["virtual_token_reserves"] == 0)
    z_not = sum(1 for k in nong if decoded[k]["status"] == "ok"
                and decoded[k]["virtual_token_reserves"] == 0)
    print(f"\n  independent check: virtual_token_reserves==0 on known-grad "
          f"{z_grad}/{len(grad)}; on sampled known-not {z_not}/{len(nong)}")
    if late_evidence:
        print(f"  flag=1 among known-not, first 5 (all should show zeroed reserves): "
              f"{late_evidence[:5]}")

    ok = (fn == 0 and tp == len(grad))
    print(f"\nVERDICT: offset {OFF_COMPLETE} recall on known graduations "
          f"{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


# ------------------------------------------------------------------------- label


def open_labels_db() -> sqlite3.Connection:
    con = sqlite3.connect(LABELS_DB, timeout=60)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        """CREATE TABLE IF NOT EXISTS window_label (
            bonding_curve TEXT PRIMARY KEY,
            mint TEXT NOT NULL,
            creator TEXT,
            create_slot INTEGER NOT NULL,
            block_time INTEGER,
            complete INTEGER,
            account_missing INTEGER NOT NULL,
            status TEXT NOT NULL,
            creator_onchain TEXT,
            virtual_token_reserves INTEGER,
            real_token_reserves INTEGER,
            data_len INTEGER,
            fetched_at_unix REAL NOT NULL
        )"""
    )
    con.execute("CREATE INDEX IF NOT EXISTS ix_wl_creator ON window_label(creator)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_wl_slot ON window_label(create_slot)")
    con.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.commit()
    return con


def cmd_label(args) -> int:
    src = sqlite3.connect(f"file:{CREATES_DB}?mode=ro", uri=True)
    creates = src.execute(
        "select bonding_curve, mint, creator, slot, block_time from create_event"
        " order by slot, transaction_index, outer_instruction_index, inner_instruction_index"
    ).fetchall()
    src.close()
    con = open_labels_db()
    done = {r[0] for r in con.execute("select bonding_curve from window_label")}
    todo = [r for r in creates if r[0] not in done]
    print(f"creates total={len(creates)} already_labeled={len(done)} todo={len(todo)}")
    if args.limit:
        todo = todo[: args.limit]
        print(f"limited to {len(todo)}")
    con.executemany(
        "INSERT OR REPLACE INTO metadata(key,value) VALUES(?,?)",
        [
            ("rpc_url", RPC_URL),
            ("program_id", PUMP_PROGRAM),
            ("complete_offset", str(OFF_COMPLETE)),
            ("discriminator", str(list(BC_DISCRIMINATOR))),
            ("source_db", CREATES_DB),
            ("started_at_unix", str(time.time())),
        ],
    )
    con.commit()

    t0 = time.time()
    for i, chunk in enumerate(batched(todo, BATCH)):
        vals = fetch_accounts([r[0] for r in chunk])
        now = time.time()
        rows = []
        for (bc, mint, creator, slot, bt), v in zip(chunk, vals):
            d = decode_account(v)
            rows.append(
                (
                    bc, mint, creator, slot, bt,
                    d["complete"],
                    1 if d["status"] == "missing" else 0,
                    d["status"],
                    d.get("creator_onchain"),
                    d.get("virtual_token_reserves"),
                    d.get("real_token_reserves"),
                    d.get("data_len"),
                    now,
                )
            )
        con.executemany(
            "INSERT OR REPLACE INTO window_label VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows
        )
        con.commit()
        if (i + 1) % 10 == 0 or (i + 1) * BATCH >= len(todo):
            n_done = len(done) + min(len(todo), (i + 1) * BATCH)
            el = time.time() - t0
            print(f"  batch {i+1}/{(len(todo)+BATCH-1)//BATCH} labeled={n_done} "
                  f"elapsed={el:.0f}s", flush=True)
        time.sleep(SLEEP_S)
    con.execute("INSERT OR REPLACE INTO metadata VALUES('finished_at_unix',?)", (str(time.time()),))
    con.commit()
    tot = con.execute("select count(*) from window_label").fetchone()[0]
    print(f"done. window_label rows={tot}")
    con.close()
    return 0


# ------------------------------------------------------------------------ report


def cmd_report(_args) -> int:
    con = sqlite3.connect(f"file:{LABELS_DB}?mode=ro", uri=True)
    tot = con.execute("select count(*) from window_label").fetchone()[0]
    src = sqlite3.connect(f"file:{CREATES_DB}?mode=ro", uri=True)
    n_creates = src.execute("select count(*) from create_event").fetchone()[0]
    src.close()
    print(f"=== coverage ===")
    print(f"create_event rows       : {n_creates}")
    print(f"window_label rows       : {tot}  ({100.0*tot/n_creates:.3f}%)")

    print(f"\n=== status breakdown (explicit, missing is its own bucket) ===")
    for status, n in con.execute(
        "select status, count(*) from window_label group by status order by count(*) desc"
    ):
        print(f"  {status:20s} {n:7d}  {100.0*n/tot:7.4f}%")

    ok = con.execute("select count(*) from window_label where status='ok'").fetchone()[0]
    grad = con.execute("select count(*) from window_label where status='ok' and complete=1").fetchone()[0]
    notg = con.execute("select count(*) from window_label where status='ok' and complete=0").fetchone()[0]
    miss = con.execute("select count(*) from window_label where account_missing=1").fetchone()[0]
    print(f"\n=== graduation ===")
    print(f"  decodable (status=ok)       : {ok}")
    print(f"  complete=1 (GRADUATED)      : {grad}")
    print(f"  complete=0                  : {notg}")
    print(f"  account_missing             : {miss}")
    if ok:
        print(f"  graduation rate / decodable : {grad}/{ok} = {100.0*grad/ok:.4f}%")
    print(f"  graduation rate / all creates: {grad}/{n_creates} = {100.0*grad/n_creates:.4f}%")
    print(f"  b11a_paths in-window subsample: 82/3932 = 2.0855%")

    # reserve cross-check
    z = con.execute("select count(*) from window_label where status='ok' and complete=1"
                    " and virtual_token_reserves=0").fetchone()[0]
    nz = con.execute("select count(*) from window_label where status='ok' and complete=0"
                     " and virtual_token_reserves=0").fetchone()[0]
    print(f"  cross-check: complete=1 with zeroed virtual_token_reserves {z}/{grad}; "
          f"complete=0 with zeroed reserves {nz}/{notg}")

    # on-chain creator vs event creator. pump.fun's IDL exposes set_creator / admin_set_creator /
    # migrate_bonding_curve_creator, so BondingCurve.creator is MUTABLE after the create and
    # therefore carries FUTURE information. Every cohort below keys on the create-event creator,
    # which is fixed at t0. creator_onchain is stored for audit only and must never be a feature.
    mism = con.execute("select count(*) from window_label where status='ok' and creator_onchain is not null"
                       " and creator is not null and creator_onchain<>creator").fetchone()[0]
    print(f"  on-chain creator != create-event creator: {mism}/{ok} "
          f"({100.0*mism/max(1,ok):.2f}%) -- set_creator is post-create, NOT used as a feature")

    # selection-bias audit of the older 3,932-curve subsample the 2.0855% figure came from
    try:
        con.execute("ATTACH ? AS p", (PATHS_DB,))
        rows = con.execute(
            """select case when p.bonding_curve is not null then 'in_b11a_paths(3932)'
                           else 'not_in_b11a_paths' end k,
                      count(*), sum(w.complete)
               from window_label w left join p.curve p using(bonding_curve)
               where w.status='ok' group by k"""
        ).fetchall()
        print(f"\n=== selection audit of the old 2.0855% subsample ===")
        for k, n, g in rows:
            print(f"  {k:20s} n={n:6d} graduated={g:5d} rate={100.0*g/n:.4f}%")
        con.execute("DETACH p")
    except sqlite3.Error as exc:
        print(f"  (paths audit skipped: {exc})")

    print(f"\n=== creator distribution over the full window ===")
    buckets = con.execute(
        """with c as (select creator, count(*) n from window_label group by creator)
           select case when n=1 then '1'
                       when n between 2 and 5 then '2-5'
                       when n between 6 and 20 then '6-20'
                       else '21+' end bucket,
                  count(*) creators, sum(n) launches
           from c group by bucket"""
    ).fetchall()
    order = {"1": 0, "2-5": 1, "6-20": 2, "21+": 3}
    tot_cre = 0
    for b, ncre, nlau in sorted(buckets, key=lambda r: order[r[0]]):
        tot_cre += ncre
        print(f"  {b:>5s} launches: creators={ncre:6d}  launches={nlau:6d}")
    print(f"  distinct creators total  : {tot_cre}")
    mx = con.execute("select creator, count(*) n from window_label group by creator"
                     " order by n desc limit 5").fetchall()
    print(f"  top creators by launches : {mx}")

    print(f"\n=== testable cohort: creates with >=1 STRICTLY EARLIER create by same creator ===")
    # Strict in-window ordering = (create_slot, transaction_index, outer_idx, inner_idx).
    # window_label keys on bonding_curve; join back to create_event for the intra-slot order.
    # Window functions do the prior-count/prior-graduation accumulation in one pass, so
    # nothing here can see a creator's FUTURE launches - that was the flaw that killed the
    # LaunchLab provenance result.
    con.execute("ATTACH ? AS cr", (CREATES_DB,))
    con.executescript(
        """CREATE TEMP TABLE ord AS
           WITH ev AS (
             SELECT w.bonding_curve, w.creator, w.complete, w.status,
                    c.slot, c.transaction_index ti, c.outer_instruction_index oi,
                    c.inner_instruction_index ii
             FROM window_label w JOIN cr.create_event c USING(bonding_curve))
           SELECT bonding_curve, creator, complete, status, slot,
                  COUNT(*) OVER w AS prior_n,
                  SUM(CASE WHEN status='ok' AND complete=1 THEN 1 ELSE 0 END) OVER w AS prior_grads,
                  SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) OVER w AS prior_labeled
           FROM ev
           WINDOW w AS (PARTITION BY creator ORDER BY slot, ti, oi, ii
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING);"""
    )
    n_any = con.execute("select count(*) from ord where prior_n>0").fetchone()[0]
    print(f"  cohort size (>=1 prior create)     : {n_any}   <- TESTABLE COHORT")
    r2 = con.execute(
        "select count(*), sum(case when complete=1 then 1 else 0 end) from ord"
        " where status='ok' and prior_labeled>0"
    ).fetchone()
    print(f"  ...with own label + >=1 labeled prior: {r2[0]}, of which graduated: {r2[1] or 0}")
    if r2[0]:
        print(f"  base rate inside that cohort       : {100.0*(r2[1] or 0)/r2[0]:.4f}%")
    r3 = con.execute(
        "select count(*), sum(case when complete=1 then 1 else 0 end) from ord"
        " where status='ok' and prior_grads>0"
    ).fetchone()
    print(f"  ...with >=1 EARLIER GRADUATED prior : {r3[0]}, of which graduated: {r3[1] or 0}")
    if r3[0]:
        print(f"  base rate GIVEN a prior graduation : {100.0*(r3[1] or 0)/r3[0]:.4f}%")
    r4 = con.execute(
        "select count(*), sum(case when complete=1 then 1 else 0 end) from ord"
        " where status='ok' and prior_labeled>0 and prior_grads=0"
    ).fetchone()
    print(f"  ...with priors but NONE graduated   : {r4[0]}, of which graduated: {r4[1] or 0}")
    if r4[0] and r3[0]:
        p_hit = (r3[1] or 0) / r3[0]
        p_miss = (r4[1] or 0) / r4[0]
        print(f"  base rate given NO prior graduation: {100.0*p_miss:.4f}%")
        if p_miss > 0:
            print(f"  >>> naive prior-graduation LIFT    : {p_hit/p_miss:.3f}x "
                  f"(chronologically clean, unweighted)")
    con.close()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe")
    v = sub.add_parser("validate")
    v.add_argument("--negatives", type=int, default=200)
    l = sub.add_parser("label")
    l.add_argument("--limit", type=int, default=0)
    sub.add_parser("report")
    args = ap.parse_args(argv)
    return {"probe": cmd_probe, "validate": cmd_validate,
            "label": cmd_label, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
