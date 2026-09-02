#!/usr/bin/env python3
"""
launchlab_provenance.py -- extract the CREATE-TIME provenance table for every
Raydium LaunchLab bonding curve ever opened.

Why this can exist at all: LaunchLab PoolState accounts are NEVER closed, so
`status` (offset 17) is a permanent, survivorship-free graduation label on every
curve, and the SAME account carries the creator pubkey and the platform config.
No per-transaction fetching is needed.

LEAKAGE IS THE PRIMARY RISK. Every field is classified CREATE-TIME vs OUTCOME
below from the on-chain Anchor IDL, and `leakcheck` MEASURES the classification
by re-reading live accounts and diffing raw bytes over a wall-clock interval.
Outcome columns are stored with an `o_` prefix and must never be used as features.

Subcommands
  layout     derive + print the PoolState byte layout from the IDL, classified
  pull       resumable bulk getProgramAccounts -> sqlite cache
  report     real counts: rows, creators, graduations, launch-count distribution
  leakcheck  measure which byte offsets actually mutate on live funding curves

Free public RPC only. No API keys.
"""
import argparse
import base64
import json
import os
import random
import sqlite3
import sys
import time
import urllib.error
import urllib.request

RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
PROGRAM = "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj"
IDL_PATH = "/home/anont/meme/research/launchpads/idl/idl_raydium launchlab.json"
DB_PATH = "/home/anont/meme/research/launchpads/census/launchlab_provenance.sqlite"

# ---------------------------------------------------------------- base58 ----
_A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58e(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = _A[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


# ------------------------------------------------------------------ layout --
# Anchor account discriminator for PoolState, taken from the IDL (not guessed).
PRIM = {"u8": 1, "u16": 2, "u32": 4, "u64": 8, "u128": 16, "i64": 8,
        "i128": 16, "bool": 1, "pubkey": 32}

# Classification of every PoolState field.
#   "create"  = written once by initialize(), never touched by buy/sell/migrate
#   "outcome" = mutated as the curve trades or migrates  -> LEAKAGE if used
#   "label"   = the graduation label itself
CLASS = {
    "epoch": ("create", "clock epoch stamped at initialize; not a trading quantity"),
    "auth_bump": ("create", "PDA bump"),
    "status": ("label", "0 funding / 1 awaiting migration / 2 migrated -- THE LABEL"),
    "base_decimals": ("create", "mint decimals fixed at create"),
    "quote_decimals": ("create", "mint decimals fixed at create"),
    "migrate_type": ("create", "0 amm / 1 cpswap, chosen at create"),
    "supply": ("create", "curve param"),
    "total_base_sell": ("create", "curve param"),
    "virtual_base": ("create", "curve param"),
    "virtual_quote": ("create", "curve param"),
    "real_base": ("outcome", "base tokens actually sold -- moves on every trade"),
    "real_quote": ("outcome", "quote actually raised -- moves on every trade"),
    "total_quote_fund_raising": ("create", "curve param: the raise TARGET, not the raise"),
    "quote_protocol_fee": ("outcome", "accumulates with volume"),
    "platform_fee": ("outcome", "accumulates with volume"),
    "migrate_fee": ("create-suspect", "IDL does not say when it is written; measured by leakcheck"),
    "vesting_schedule": ("create-suspect", "params are create-time but allocated_share_amount may move on claims"),
    "global_config": ("create", "protocol config pubkey"),
    "platform_config": ("create", "PLATFORM/venue identity -- create-time feature"),
    "base_mint": ("create", "token identity"),
    "quote_mint": ("create", "SOL/USDC etc"),
    "base_vault": ("create", "vault PDA"),
    "quote_vault": ("create", "vault PDA"),
    "creator": ("create", "CREATOR PUBKEY -- the provenance feature"),
    "token_program_flag": ("create", "spl-token vs token-2022"),
    "amm_creator_fee_on": ("create", "fee routing choice at create"),
    "platform_vesting_share": ("create", "create param"),
    "padding": ("create", "zero padding"),
}


def derive_layout():
    idl = json.load(open(IDL_PATH))
    types = {t["name"]: t["type"] for t in idl["types"]}
    disc = [a["discriminator"] for a in idl["accounts"] if a["name"] == "PoolState"][0]

    def size(ty):
        if isinstance(ty, str):
            return PRIM[ty]
        if "array" in ty:
            e, n = ty["array"]
            return size(e) * n
        if "defined" in ty:
            tt = types[ty["defined"]["name"]]
            if tt["kind"] == "struct":
                return sum(size(f["type"]) for f in tt["fields"])
            if tt["kind"] == "enum":
                return 1
        raise ValueError(ty)

    off, rows = 8, []
    for f in types["PoolState"]["fields"]:
        rows.append((off, size(f["type"]), f["name"], f["type"]))
        off += size(f["type"])
    return bytes(disc), rows, off


# Slice window: offset 17 (status) .. offset 365 (end of creator). One contiguous
# window that carries the label, every create-time scalar, the platform config
# and the creator -- so one pass over the program yields the whole table.
SL_OFF, SL_LEN = 17, 348
R = {  # field -> offset RELATIVE to the slice
    "status": 0, "base_decimals": 1, "quote_decimals": 2, "migrate_type": 3,
    "supply": 4, "total_base_sell": 12, "virtual_base": 20, "virtual_quote": 28,
    "real_base": 36, "real_quote": 44, "total_quote_fund_raising": 52,
    "quote_protocol_fee": 60, "platform_fee": 68, "migrate_fee": 76,
    "vest_total_locked": 84, "vest_cliff": 92, "vest_unlock": 100,
    "vest_start": 108, "vest_alloc": 116,
    "global_config": 124, "platform_config": 156, "base_mint": 188,
    "quote_mint": 220, "base_vault": 252, "quote_vault": 284, "creator": 316,
}


def u64(b, o):
    return int.from_bytes(b[o:o + 8], "little")


# SQLite INTEGER is signed 64-bit, but these fields are u64. Two values of
# virtual_base in the corpus exceed 2**63 (legitimate: for LaunchLab's linear
# curve virtual_base is the price-slope parameter `a`, not a token amount).
# Store the two's-complement reinterpretation -- a lossless bijection. Recover
# the unsigned value with:  v + 2**64 if v < 0 else v.
WRAPPED = {}


def sq(v, name=""):
    if v >= 1 << 63:
        WRAPPED[name] = WRAPPED.get(name, 0) + 1
        return v - (1 << 64)
    return v


# --------------------------------------------------------------------- rpc --
class Rpc:
    def __init__(self, url=RPC_URL, delay=0.35):
        self.url = url
        self.delay = delay
        self.last = 0.0
        self.calls = 0

    def call(self, method, params, timeout=300, tries=6):
        for attempt in range(tries):
            gap = self.delay - (time.time() - self.last)
            if gap > 0:
                time.sleep(gap)
            self.last = time.time()
            self.calls += 1
            body = json.dumps({"jsonrpc": "2.0", "id": 1,
                               "method": method, "params": params}).encode()
            req = urllib.request.Request(
                self.url, data=body, headers={"Content-Type": "application/json"})
            try:
                r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
            except Exception as e:                       # noqa: BLE001
                wait = min(60, 2 ** attempt * 2)
                print(f"    [rpc] {type(e).__name__} {str(e)[:120]} -> retry in {wait}s",
                      flush=True)
                time.sleep(wait)
                continue
            if "error" in r:
                msg = json.dumps(r["error"])[:200]
                wait = min(60, 2 ** attempt * 2)
                print(f"    [rpc] error {msg} -> retry in {wait}s", flush=True)
                time.sleep(wait)
                continue
            return r["result"]
        raise RuntimeError(f"{method} failed after {tries} tries")


def gpa(rpc, disc_b64, filters, sl_off, sl_len):
    flt = [{"memcmp": {"offset": 0, "bytes": disc_b64, "encoding": "base64"}}] + filters
    cfg = {"encoding": "base64", "filters": flt}
    if sl_len is not None:
        cfg["dataSlice"] = {"offset": sl_off, "length": sl_len}
    return rpc.call("getProgramAccounts", [PROGRAM, cfg])


# ---------------------------------------------------------------- sqlite -----
DDL = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS pubkeys(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, pk TEXT NOT NULL,
  UNIQUE(kind, pk));
CREATE TABLE IF NOT EXISTS pools(
  pool TEXT PRIMARY KEY,
  creator TEXT NOT NULL,
  platform_config INTEGER NOT NULL,
  status INTEGER NOT NULL,
  graduated INTEGER NOT NULL,
  -- create-time (safe features)
  migrate_type INTEGER, base_decimals INTEGER, quote_decimals INTEGER,
  supply INTEGER, total_base_sell INTEGER, virtual_base INTEGER,
  virtual_quote INTEGER, total_quote_fund_raising INTEGER,
  vest_total_locked INTEGER, vest_cliff INTEGER, vest_unlock INTEGER,
  vest_start INTEGER, vest_alloc INTEGER,
  global_config INTEGER, quote_mint INTEGER, base_mint TEXT,
  -- OUTCOME columns, o_ prefix. Audit only. NEVER a feature.
  o_real_base INTEGER, o_real_quote INTEGER,
  o_quote_protocol_fee INTEGER, o_platform_fee INTEGER, o_migrate_fee INTEGER);
CREATE TABLE IF NOT EXISTS partitions(
  key TEXT PRIMARY KEY, status INTEGER, cbyte INTEGER, n INTEGER,
  short INTEGER, elapsed REAL, done_utc TEXT);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""


def opendb(path=DB_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path, timeout=120)
    db.executescript(DDL)
    return db


class PkCache:
    def __init__(self, db):
        self.db = db
        self.m = {}
        for i, k, p in db.execute("SELECT id,kind,pk FROM pubkeys"):
            self.m[(k, p)] = i

    def id(self, kind, pk):
        key = (kind, pk)
        if key not in self.m:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO pubkeys(kind,pk) VALUES(?,?)", key)
            if cur.lastrowid and cur.rowcount:
                self.m[key] = cur.lastrowid
            else:
                self.m[key] = self.db.execute(
                    "SELECT id FROM pubkeys WHERE kind=? AND pk=?", key).fetchone()[0]
        return self.m[key]


COLS = ("pool creator platform_config status graduated migrate_type base_decimals "
        "quote_decimals supply total_base_sell virtual_base virtual_quote "
        "total_quote_fund_raising vest_total_locked vest_cliff vest_unlock "
        "vest_start vest_alloc global_config quote_mint base_mint "
        "o_real_base o_real_quote o_quote_protocol_fee o_platform_fee "
        "o_migrate_fee").split()
INS = f"INSERT OR REPLACE INTO pools({','.join(COLS)}) VALUES({','.join('?'*len(COLS))})"


def decode(pubkey, b, pk):
    st = b[R["status"]]
    return (
        pubkey,
        b58e(b[R["creator"]:R["creator"] + 32]),
        pk.id("platform", b58e(b[R["platform_config"]:R["platform_config"] + 32])),
        st, 1 if st == 2 else 0,
        b[R["migrate_type"]], b[R["base_decimals"]], b[R["quote_decimals"]],
        sq(u64(b, R["supply"]), "supply"),
        sq(u64(b, R["total_base_sell"]), "total_base_sell"),
        sq(u64(b, R["virtual_base"]), "virtual_base"),
        sq(u64(b, R["virtual_quote"]), "virtual_quote"),
        sq(u64(b, R["total_quote_fund_raising"]), "total_quote_fund_raising"),
        sq(u64(b, R["vest_total_locked"]), "vest_total_locked"),
        sq(u64(b, R["vest_cliff"]), "vest_cliff"),
        sq(u64(b, R["vest_unlock"]), "vest_unlock"),
        sq(u64(b, R["vest_start"]), "vest_start"),
        sq(u64(b, R["vest_alloc"]), "vest_alloc"),
        pk.id("global", b58e(b[R["global_config"]:R["global_config"] + 32])),
        pk.id("quote", b58e(b[R["quote_mint"]:R["quote_mint"] + 32])),
        b58e(b[R["base_mint"]:R["base_mint"] + 32]),
        sq(u64(b, R["real_base"]), "real_base"),
        sq(u64(b, R["real_quote"]), "real_quote"),
        sq(u64(b, R["quote_protocol_fee"]), "quote_protocol_fee"),
        sq(u64(b, R["platform_fee"]), "platform_fee"),
        sq(u64(b, R["migrate_fee"]), "migrate_fee"),
    )


# ------------------------------------------------------------------ pull -----
def cmd_pull(args):
    disc, _, _ = derive_layout()
    disc_b64 = base64.b64encode(disc).decode()
    db = opendb(args.db)
    pk = PkCache(db)
    rpc = Rpc(delay=args.delay)

    # Partition plan. status 2 (migrated, ~13.7k) and status 1 (~0) are small
    # enough for a single pass -- the positive class is pulled COMPLETE, never
    # sampled. status 0 (~1.28M) is split into 256 disjoint, exhaustive
    # partitions on the first byte of the creator pubkey (offset 333).
    plan = [("s2", 2, None), ("s1", 1, None)]
    cbytes = list(range(256))
    if args.sample_cbytes:
        rng = random.Random(args.seed)
        cbytes = sorted(rng.sample(cbytes, args.sample_cbytes))
        db.execute("INSERT OR REPLACE INTO meta VALUES('funding_sampling',?)",
                   (json.dumps({"method": "random subset of the 256 creator-byte0 "
                                          "partitions (uniform over pubkey space)",
                                "seed": args.seed, "k": args.sample_cbytes,
                                "bytes": cbytes}),))
    else:
        db.execute("INSERT OR REPLACE INTO meta VALUES('funding_sampling',"
                   "'none -- all 256 creator-byte0 partitions, complete census')")
    plan += [(f"s0.{c:03d}", 0, c) for c in cbytes]
    db.commit()

    done = {k for (k,) in db.execute("SELECT key FROM partitions")}
    todo = [p for p in plan if p[0] not in done]
    print(f"[pull] rpc={RPC_URL}", flush=True)
    print(f"[pull] slice offset={SL_OFF} len={SL_LEN} (status..creator)", flush=True)
    print(f"[pull] partitions total={len(plan)} done={len(done)} todo={len(todo)}",
          flush=True)

    t0 = time.time()
    for i, (key, status, cbyte) in enumerate(todo):
        flt = [{"memcmp": {"offset": 17,
                           "bytes": base64.b64encode(bytes([status])).decode(),
                           "encoding": "base64"}}]
        if cbyte is not None:
            flt.append({"memcmp": {"offset": 333,
                                   "bytes": base64.b64encode(bytes([cbyte])).decode(),
                                   "encoding": "base64"}})
        t = time.time()
        res = gpa(rpc, disc_b64, flt, SL_OFF, SL_LEN)
        el = time.time() - t
        rows, short = [], 0
        for a in res:
            b = base64.b64decode(a["account"]["data"][0])
            if len(b) < SL_LEN:
                short += 1
                continue
            rows.append(decode(a["pubkey"], b, pk))
        db.executemany(INS, rows)
        db.execute("INSERT OR REPLACE INTO partitions VALUES(?,?,?,?,?,?,?)",
                   (key, status, cbyte, len(res), short, el,
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        db.commit()
        eta = (time.time() - t0) / (i + 1) * (len(todo) - i - 1)
        print(f"[pull] {key} status={status} n={len(res)} short={short} "
              f"{el:.1f}s  ({i+1}/{len(todo)}, eta {eta/60:.1f}m)", flush=True)

    db.execute("CREATE INDEX IF NOT EXISTS ix_creator ON pools(creator)")
    db.execute("CREATE INDEX IF NOT EXISTS ix_grad ON pools(graduated)")
    db.execute("INSERT OR REPLACE INTO meta VALUES('pull_done_utc',?)",
               (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),))
    db.execute("INSERT OR REPLACE INTO meta VALUES('u64_wrapped_to_signed',?)",
               (json.dumps(WRAPPED),))
    db.commit()
    print(f"[pull] DONE rpc_calls={rpc.calls} elapsed={(time.time()-t0)/60:.1f}m",
          flush=True)


# ---------------------------------------------------------------- report -----
def cmd_report(args):
    db = opendb(args.db)
    q = lambda s, *a: db.execute(s, a).fetchone()[0]          # noqa: E731
    out = {}

    parts = db.execute("SELECT status, COUNT(*), SUM(n), SUM(short) "
                       "FROM partitions GROUP BY status").fetchall()
    rows = q("SELECT COUNT(*) FROM pools")
    grads = q("SELECT COUNT(*) FROM pools WHERE graduated=1")
    creators = q("SELECT COUNT(DISTINCT creator) FROM pools")
    plats = q("SELECT COUNT(DISTINCT platform_config) FROM pools")

    print("=" * 74)
    print("LAUNCHLAB PROVENANCE TABLE -- MEASURED")
    print("=" * 74)
    print(f"db                    {args.db}")
    print(f"size_on_disk          {os.path.getsize(args.db)/1e6:.1f} MB")
    for k, v in db.execute("SELECT k,v FROM meta"):
        print(f"{k:<22}{v[:110]}")
    print("\n-- partitions (RPC-reported n vs rows stored) --")
    tot_n = tot_short = 0
    for st, np_, n, sh in parts:
        print(f"  status={st}  partitions={np_:>4}  accounts_returned={n:>9}  "
              f"short_data={sh}")
        tot_n += n or 0
        tot_short += sh or 0
    print(f"  TOTAL accounts returned by RPC: {tot_n}   short/malformed: {tot_short}")
    print(f"  rows stored in table:           {rows}")
    print(f"  completeness (stored/returned): {rows/tot_n:.6f}" if tot_n else "")

    print("\n-- headline counts --")
    print(f"  rows (curves)               {rows}")
    print(f"  distinct creators           {creators}")
    print(f"  distinct platform_configs   {plats}")
    print(f"  graduated (status=2)        {grads}")
    print(f"  awaiting migration (st=1)   {q('SELECT COUNT(*) FROM pools WHERE status=1')}")
    print(f"  funding (status=0)          {q('SELECT COUNT(*) FROM pools WHERE status=0')}")
    print(f"  base graduation rate p      {grads/rows:.6f}" if rows else "")
    out["rows"], out["creators"], out["graduated"] = rows, creators, grads

    # creator launch-count distribution
    print("\n-- creator launch-count distribution --")
    buckets = [("1", 1, 1), ("2-5", 2, 5), ("6-20", 6, 20), ("21+", 21, 1 << 62)]
    dist = {}
    for name, lo, hi in buckets:
        nc, npool, ng = db.execute(
            "SELECT COUNT(*), SUM(n), SUM(g) FROM "
            "(SELECT creator, COUNT(*) n, SUM(graduated) g FROM pools "
            " GROUP BY creator) WHERE n BETWEEN ? AND ?", (lo, hi)).fetchone()
        dist[name] = dict(creators=nc, launches=npool or 0, graduations=ng or 0)
        print(f"  launches {name:<5} creators={nc:>9}  curves={npool or 0:>9}  "
              f"graduations={ng or 0:>7}  "
              f"p={(ng or 0)/(npool or 1):.6f}")
    out["creator_launch_distribution"] = dist

    # THE quantity the whole test depends on
    ng_multi, np_multi = db.execute(
        "SELECT SUM(g), SUM(n) FROM (SELECT creator, COUNT(*) n, SUM(graduated) g "
        "FROM pools GROUP BY creator) WHERE n>1").fetchone()
    ng_single, np_single = db.execute(
        "SELECT SUM(g), SUM(n) FROM (SELECT creator, COUNT(*) n, SUM(graduated) g "
        "FROM pools GROUP BY creator) WHERE n=1").fetchone()
    print("\n-- THE LOAD-BEARING QUANTITY --")
    print(f"  graduations from creators with >1 launch : {ng_multi or 0} "
          f"of {np_multi or 0} curves  (p={(ng_multi or 0)/(np_multi or 1):.6f})")
    print(f"  graduations from one-launch creators     : {ng_single or 0} "
          f"of {np_single or 0} curves  (p={(ng_single or 0)/(np_single or 1):.6f})")
    print(f"  share of all graduations that are repeat-creator: "
          f"{(ng_multi or 0)/(grads or 1):.4f}")
    out["grads_from_repeat_creators"] = ng_multi or 0
    out["curves_from_repeat_creators"] = np_multi or 0

    # repeat-graduator concentration
    print("\n-- creators with >=2 graduations --")
    r2 = db.execute("SELECT COUNT(*), SUM(g) FROM (SELECT creator, SUM(graduated) g "
                    "FROM pools GROUP BY creator) WHERE g>=2").fetchone()
    print(f"  creators={r2[0]}  their graduations={r2[1] or 0} "
          f"({(r2[1] or 0)/(grads or 1):.4f} of all graduations)")
    print("  top creators by graduations:")
    for c, n, g in db.execute(
            "SELECT creator, COUNT(*) n, SUM(graduated) g FROM pools GROUP BY creator "
            "ORDER BY g DESC, n DESC LIMIT 10"):
        print(f"    {c}  launches={n:<6} grads={g}")

    print("\n-- platform_config split --")
    for p, n, g in db.execute(
            "SELECT (SELECT pk FROM pubkeys WHERE id=platform_config), COUNT(*), "
            "SUM(graduated) FROM pools GROUP BY platform_config "
            "ORDER BY COUNT(*) DESC LIMIT 8"):
        print(f"  {p}  curves={n:<9} grads={g:<6} p={g/n:.6f}")

    if args.json:
        open(args.json, "w").write(json.dumps(out, indent=2))
        print(f"\n[report] json -> {args.json}")


# -------------------------------------------------------------- leakcheck ----
def cmd_leakcheck(args):
    """Differential byte-diff on LIVE accounts: the only honest way to know which
    offsets are outcomes. Snapshot N funding curves, wait, re-read, diff."""
    db = opendb(args.db)
    rpc = Rpc(delay=args.delay)
    rng = random.Random(args.seed)
    pool_ids = [p for (p,) in db.execute(
        "SELECT pool FROM pools WHERE status=0 AND o_real_quote>0 "
        "ORDER BY RANDOM() LIMIT ?", (args.n,))]
    if not pool_ids:
        print("[leak] no traded funding pools in db; run pull first")
        return
    print(f"[leak] sampling {len(pool_ids)} funding curves that have traded "
          f"(o_real_quote>0), wait={args.wait}s", flush=True)

    def snap():
        out = {}
        for i in range(0, len(pool_ids), 100):
            chunk = pool_ids[i:i + 100]
            res = rpc.call("getMultipleAccounts",
                           [chunk, {"encoding": "base64"}])["value"]
            for pid, a in zip(chunk, res):
                if a:
                    out[pid] = base64.b64decode(a["data"][0])
        return out

    a = snap()
    t_a = time.time()
    time.sleep(max(0, args.wait))
    b = snap()
    dt = time.time() - t_a

    _, rows, _ = derive_layout()
    changed = {}
    n_cmp = 0
    for pid in a:
        if pid not in b or len(a[pid]) != len(b[pid]):
            continue
        n_cmp += 1
        for off, ln, name, _ty in rows:
            if a[pid][off:off + ln] != b[pid][off:off + ln]:
                changed[name] = changed.get(name, 0) + 1
    print(f"[leak] compared {n_cmp} accounts over {dt:.0f}s wall clock")
    print(f"{'field':<26}{'offset':>7}{'changed':>9}  classification")
    verdict_ok = True
    for off, ln, name, _ty in rows:
        c = changed.get(name, 0)
        cls = CLASS.get(name, ("?", ""))[0]
        flag = ""
        if c > 0 and cls.startswith("create"):
            flag = "  <<< MUTATES -- NOT A CREATE-TIME FEATURE"
            verdict_ok = False
        print(f"{name:<26}{off:>7}{c:>9}  {cls}{flag}")
    ctrl = changed.get("real_base", 0) + changed.get("real_quote", 0)
    print(f"\n[leak] POSITIVE CONTROL (real_base/real_quote moved): {ctrl}")
    if ctrl == 0:
        print("[leak] NO VERDICT. The control did not fire: no sampled curve traded "
              "during the window, so 'nothing changed' is a statement about the "
              "sample being dead, not about immutability. Use `leakdiff`, or widen "
              "--wait / bias the sample toward curves near their raise target.")
        return
    print(f"[leak] VERDICT: {'no create-classified field mutated' if verdict_ok else 'LEAKAGE FOUND above'}"
          f"  (n={n_cmp}, curves that actually moved={ctrl}, window={dt:.0f}s)")
    print("[leak] NOTE: power is set by the number of curves that MOVED, not by n. "
          "A null with a small control is weak evidence.")


def cmd_leakdiff(args):
    """The honest leakage test. `leakcheck` (snapshot / wait / re-read on random
    funding curves) is USELESS on its own: almost every funding curve is
    abandoned, so it returns "nothing changed" for the outcome fields too and the
    null is uninformative. This version uses the stored pull as snapshot A and a
    fresh read as snapshot B -- a window of tens of minutes over ~50k curves --
    and REFUSES a verdict unless the positive control (an outcome field actually
    moved on some curve) fires."""
    disc, _, _ = derive_layout()
    disc_b64 = base64.b64encode(disc).decode()
    db = opendb(args.db)
    pk = PkCache(db)
    rpc = Rpc(delay=args.delay)
    rng = random.Random(args.seed)
    cbytes = sorted(rng.sample(range(256), args.partitions))

    changed = {c: 0 for c in COLS[1:]}
    n_cmp = 0
    ages = []
    for cb in cbytes:
        row = db.execute("SELECT done_utc FROM partitions WHERE key=?",
                         (f"s0.{cb:03d}",)).fetchone()
        if not row:
            continue
        age = time.time() - time.mktime(time.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ"))
        ages.append(age)
        flt = [{"memcmp": {"offset": 17, "bytes": base64.b64encode(bytes([0])).decode(),
                           "encoding": "base64"}},
               {"memcmp": {"offset": 333, "bytes": base64.b64encode(bytes([cb])).decode(),
                           "encoding": "base64"}}]
        res = gpa(rpc, disc_b64, flt, SL_OFF, SL_LEN)
        # stored rows for exactly this partition
        want = [a["pubkey"] for a in res]
        stored = {}
        for i in range(0, len(want), 900):
            chunk = want[i:i + 900]
            qs = ",".join("?" * len(chunk))
            for r in db.execute(
                    f"SELECT {','.join(COLS)} FROM pools WHERE pool IN ({qs})", chunk):
                stored[r[0]] = r
        for a in res:
            b = base64.b64decode(a["account"]["data"][0])
            if len(b) < SL_LEN or a["pubkey"] not in stored:
                continue
            live = decode(a["pubkey"], b, pk)
            old = stored[a["pubkey"]]
            n_cmp += 1
            for j, c in enumerate(COLS[1:], start=1):
                if live[j] != old[j]:
                    changed[c] += 1
        print(f"  [leakdiff] cbyte={cb:>3} live={len(res)} matched={len(stored)} "
              f"window={age/60:.0f}m", flush=True)

    ctrl = changed["o_real_quote"] + changed["o_real_base"]
    print(f"\n[leakdiff] compared {n_cmp} curves; snapshot age "
          f"{min(ages)/60:.0f}-{max(ages)/60:.0f} min")
    print(f"{'column':<28}{'changed':>9}  class")
    creat_bad = []
    for c in COLS[1:]:
        cls = "OUTCOME" if c.startswith("o_") else ("LABEL" if c in ("status", "graduated")
                                                    else "create")
        flag = ""
        if changed[c] and cls == "create":
            flag = "   <<< MUTATES: NOT A CREATE-TIME FEATURE"
            creat_bad.append(c)
        print(f"{c:<28}{changed[c]:>9}  {cls}{flag}")
    print(f"\n[leakdiff] POSITIVE CONTROL "
          f"(o_real_base/o_real_quote moved): {ctrl}")
    if ctrl == 0:
        print("[leakdiff] NO VERDICT -- control did not fire, the window caught no "
              "trading. A null here says nothing about immutability.")
    elif creat_bad:
        print(f"[leakdiff] LEAKAGE: {creat_bad} mutate post-create.")
    else:
        print("[leakdiff] PASS: outcome columns moved, every create-classified "
              "column held constant across the window.")


def cmd_layout(args):
    disc, rows, end = derive_layout()
    print(f"PoolState  program={PROGRAM}")
    print(f"discriminator = {disc.hex()}   account size = {end} bytes "
          f"(8 disc + {end-8} data)")
    print(f"\n{'off':>4} {'len':>4}  {'field':<26}{'class':<15}note")
    print("-" * 100)
    for off, ln, name, _ty in rows:
        cls, note = CLASS.get(name, ("?", "UNCLASSIFIED"))
        print(f"{off:>4} {ln:>4}  {name:<26}{cls:<15}{note}")
    print("-" * 100)
    print(f"\nCREATE-TIME FEATURES USABLE AT t=0 (no price, no trade has happened):")
    for off, ln, name, _ty in rows:
        if CLASS.get(name, ("?",))[0] == "create":
            print(f"   @{off:<4} {name}")
    print(f"\nOUTCOME / MUTABLE -- USING ANY OF THESE AS A FEATURE IS LEAKAGE:")
    for off, ln, name, _ty in rows:
        if CLASS.get(name, ("?",))[0] in ("outcome", "label", "create-suspect"):
            print(f"   @{off:<4} {name:<26}({CLASS[name][0]})")
    print(f"\nPULL SLICE: offset={SL_OFF} length={SL_LEN}  -> covers status@17 "
          f"through end of creator@333+32=365")
    print("relative offsets inside the slice:")
    for k, v in sorted(R.items(), key=lambda kv: kv[1]):
        print(f"   +{v:<4} {k}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("layout"); p.set_defaults(f=cmd_layout)
    p = sub.add_parser("pull"); p.set_defaults(f=cmd_pull)
    p.add_argument("--db", default=DB_PATH)
    p.add_argument("--delay", type=float, default=0.35)
    p.add_argument("--sample-cbytes", type=int, default=0,
                   help="if >0, sample this many of the 256 creator-byte0 "
                        "partitions for the funding class (migrated always complete)")
    p.add_argument("--seed", type=int, default=20260902)
    p = sub.add_parser("report"); p.set_defaults(f=cmd_report)
    p.add_argument("--db", default=DB_PATH); p.add_argument("--json", default=None)
    p = sub.add_parser("leakdiff"); p.set_defaults(f=cmd_leakdiff)
    p.add_argument("--db", default=DB_PATH)
    p.add_argument("--partitions", type=int, default=12)
    p.add_argument("--delay", type=float, default=0.35)
    p.add_argument("--seed", type=int, default=20260902)
    p = sub.add_parser("leakcheck"); p.set_defaults(f=cmd_leakcheck)
    p.add_argument("--db", default=DB_PATH); p.add_argument("--n", type=int, default=400)
    p.add_argument("--wait", type=int, default=300)
    p.add_argument("--delay", type=float, default=0.35)
    p.add_argument("--seed", type=int, default=20260902)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
