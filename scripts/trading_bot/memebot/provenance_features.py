#!/usr/bin/env python3
"""
provenance_features.py -- per-curve provenance feature extractor for the b11a
survivorship-free pump.fun launch cohort.

WHAT THIS IS
------------
One row per bonding curve, carrying every feature that has been *confirmed
computable* from the data already on disk, plus the graduation label.  Nothing
here is fetched from the network; nothing here is assumed.  Every column is
either read directly out of a collected artifact or derived from one by an
arithmetic identity that is asserted in --selftest.

SOURCES (all read-only, all opened with mode=ro)
  research/b11a/b11a_paths.sqlite       curve list, graduation label, price path
  research/b11a/b11a_identity.sqlite    creator / create_user per curve
  research/b11a/b11a_creates.sqlite     the FULL 23h create window (33,866), URIs
  research/b11a/b11a_signatures.sqlite  slot->block_time, failed-tx census
  research/b11a/b11a_bodies.sqlite      instructions + reserves + raw tx bodies

OUTPUT
  research/b11a/derived/provenance_features.sqlite   (table `features`, 1 row/curve)

The cache is content-stamped: `manifest` records the extractor's own sha256 and
the (size, mtime, row-count) of every source database.  Re-running is a no-op
unless a stamp changed or --rebuild is passed.

HONESTY NOTES BAKED INTO THE SCHEMA
-----------------------------------
* `top10_flow_share` is the on-curve *net flow* concentration.  It is DEGENERATE
  (it equals 1.0 for most curves because the median curve has 0 net-positive
  on-curve holders in its first minute).  It is emitted only so that the
  degeneracy is visible, and `graduation_test.py` refuses to use it.
* `top10_balance_share` is the real thing: a holder snapshot at t0+60s
  reconstructed by replaying `meta.postTokenBalances` (absolute post-balances,
  not deltas) across every collected transaction on the curve in (slot,
  transaction_index) order and keeping each owner's last known balance.
  CAVEAT, recorded and not hidden: the collected signature set is the set of
  transactions touching the bonding curve, so a holder who received tokens by a
  plain SPL transfer that never touched the curve is invisible.  The snapshot is
  exact over trading holders, a lower bound over all holders.
* t0 is the block_time of the curve's create slot.  m60 = price(t<=t0+60s)/floor
  where floor is the CreateEvent price, which is also the all-time minimum for
  every curve in this cohort (asserted, not assumed -- see `ever_below_floor`).
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import sqlite3
import sys
import time
import zlib

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
B11A = os.path.join(REPO, "research", "b11a")
DEFAULT_CACHE = os.path.join(B11A, "derived", "provenance_features.sqlite")

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# Account indices of (bonding_curve, user) per instruction, read from the pinned
# IDL research/pump_idl_9c82f61.json.  PumpSwap (pAMMBay...) also exposes
# buy/sell with a DIFFERENT layout, hence the hard program_id filter below.
ACCOUNT_INDEX = {
    "create":                  (2, 7),
    "create_v2":               (2, 5),
    "buy":                     (3, 6),
    "buy_exact_sol_in":        (3, 6),
    "sell":                    (3, 6),
    "buy_v2":                  (10, 13),
    "buy_exact_quote_in_v2":   (10, 13),
    "sell_v2":                 (10, 13),
}
SIDE = {
    "buy": 1, "buy_exact_sol_in": 1, "buy_v2": 1, "buy_exact_quote_in_v2": 1,
    "sell": -1, "sell_v2": -1,
    "create": 0, "create_v2": 0,
}

# real_token_reserves at create -- the tokens actually sellable on the curve.
# Verified below against the collected CreateEvent observations, not assumed.
CURVE_SELLABLE_SUPPLY = 793_100_000_000_000

SNIPER_SLOT_WINDOWS = (1, 5, 20)
MINUTE = 60


def _ro(path: str) -> sqlite3.Connection:
    if not os.path.exists(path):
        raise SystemExit("missing source database: %s" % path)
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True)


def _self_sha256() -> str:
    with open(os.path.abspath(__file__), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _source_stamp(paths: dict) -> dict:
    out = {}
    for name, p in paths.items():
        st = os.stat(p)
        out[name] = {"path": p, "bytes": st.st_size, "mtime_ns": st.st_mtime_ns}
    return out


def _log(msg: str) -> None:
    sys.stderr.write("[prov] %s\n" % msg)
    sys.stderr.flush()


# --------------------------------------------------------------------------
# stage 1 -- curves, labels, identities
# --------------------------------------------------------------------------
def load_curves(paths_db: str, identity_db: str) -> dict:
    p, i = _ro(paths_db), _ro(identity_db)
    ident = {
        r[0]: (r[1], r[2], r[3], r[4])
        for r in i.execute(
            "select bonding_curve, creator, create_user, t0_kind, t0_slot from identity")
    }
    curves = {}
    for (bc, mint, cs, ct, co, ci, comp, tobs, regime) in p.execute(
        "select bonding_curve, mint, create_slot, create_transaction_index,"
        " create_outer_index, create_inner_index, complete_slot,"
        " trade_observations, regime from curve"
    ):
        cr = ident.get(bc, (None, None, None, None))
        curves[bc] = {
            "mint": mint, "create_slot": cs, "create_tx": ct,
            "create_outer": co, "create_inner": ci,
            "complete_slot": comp, "graduated": 1 if comp is not None else 0,
            "trade_observations": tobs, "regime": regime,
            "creator": cr[0], "create_user": cr[1], "t0_kind": cr[2],
        }
    p.close(); i.close()
    return curves


def load_slot_times(signatures_db: str, creates_db: str) -> dict:
    """slot -> unix block_time.  Two independent sources; signatures wins, and any
    disagreement is counted and reported rather than silently resolved."""
    s, c = _ro(signatures_db), _ro(creates_db)
    st = {}
    for slot, bt in s.execute(
        "select slot, min(block_time) from signature_observation"
        " where slot is not null and block_time is not null group by slot"
    ):
        st[slot] = bt
    disagree = 0
    added = 0
    for slot, bt in c.execute(
        "select slot, block_time from slot_scan where block_time is not null"
    ):
        if slot in st:
            if st[slot] != bt:
                disagree += 1
        else:
            st[slot] = bt
            added += 1
    s.close(); c.close()
    _log("slot_time: %d slots (%d added from slot_scan, %d disagreements)"
         % (len(st), added, disagree))
    return st, disagree


# --------------------------------------------------------------------------
# stage 2 -- price path (from the decoded reserve observations)
# --------------------------------------------------------------------------
def price_features(paths_db: str, curves: dict, slot_time: dict) -> dict:
    """floor price, price at t0+60s / t0+300s, entry premium m, all-time min."""
    p = _ro(paths_db)
    out = {}
    cur_bc = None
    path = []

    def flush(bc, rows):
        if bc is None or not rows:
            return
        c = curves.get(bc)
        if c is None:
            return
        t0 = slot_time.get(c["create_slot"])
        priced = [(slot_time.get(s), vq / vt) for (s, k, vq, vt) in rows if vt and vq]
        if not priced:
            return
        floor = priced[0][1]
        minpx = min(px for (_, px) in priced)
        last = priced[-1][1]

        def at(horizon):
            if t0 is None:
                return None
            seen = [px for (bt, px) in priced if bt is not None and bt <= t0 + horizon]
            return seen[-1] if seen else None

        px60, px300 = at(MINUTE), at(5 * MINUTE)
        out[bc] = {
            "t0_block_time": t0,
            "n_priced_obs": len(priced),
            "floor_px": floor,
            "px60": px60, "px300": px300,
            "m60": (px60 / floor) if px60 else None,
            "m300": (px300 / floor) if px300 else None,
            "last_px": last,
            "min_px": minpx,
            "ever_below_floor": 1 if minpx < floor * (1 - 1e-12) else 0,
        }

    for bc, slot, kind, vq, vt in p.execute(
        "select bonding_curve, slot, kind, virtual_quote, virtual_token"
        " from observation order by bonding_curve, slot, transaction_index,"
        " outer_index, inner_index"
    ):
        if bc != cur_bc:
            flush(cur_bc, path)
            cur_bc, path = bc, []
        path.append((slot, kind, vq, vt))
    flush(cur_bc, path)
    p.close()
    return out


# --------------------------------------------------------------------------
# stage 3 -- trade actions: who bought/sold how many tokens, when
# --------------------------------------------------------------------------
def load_actions(bodies_db: str):
    """Yield (slot, tx, outer, inner, name, side, bonding_curve, wallet, tokens).

    `tokens` is the absolute token amount moved, derived from the reserve delta
    (virtual_token_before - virtual_token_after for a buy).  The instruction rows
    carry no data blob, so the reserve delta is the ONLY source of amounts.
    """
    b = _ro(bodies_db)
    names = ",".join("'%s'" % n for n in ACCOUNT_INDEX)
    q = (
        "select i.slot, i.transaction_index, i.outer_index, i.inner_index,"
        " i.idl_name, i.accounts_json,"
        " r.virtual_token_before, r.virtual_token_after,"
        " r.virtual_quote_before, r.virtual_quote_after"
        " from instruction i left join reserve_observation r"
        "   on r.slot = i.slot and r.transaction_index = i.transaction_index"
        "  and r.outer_index = i.outer_index and r.inner_index = i.inner_index"
        " where i.target = 1 and i.program_id = ? and i.idl_name in (%s)" % names
    )
    for row in b.execute(q, (PUMP_PROGRAM,)):
        slot, tx, outer, inner, name, aj, vtb, vta, vqb, vqa = row
        acc = json.loads(aj) if aj else []
        bi, ui = ACCOUNT_INDEX[name]
        bc = acc[bi] if len(acc) > bi else None
        wallet = acc[ui] if len(acc) > ui else None
        side = SIDE[name]
        tokens = None
        if vtb is not None and vta is not None:
            tokens = (vtb - vta) if side > 0 else (vta - vtb)
        yield (slot, tx, outer, inner, name, side, bc, wallet, tokens)
    b.close()


# --------------------------------------------------------------------------
# stage 4 -- the create window: serial creators, metadata URI host, flags
# --------------------------------------------------------------------------
def window_features(creates_db: str) -> dict:
    c = _ro(creates_db)
    rows = list(c.execute(
        "select slot, transaction_index, bonding_curve, creator, is_mayhem_mode,"
        " is_cashback_enabled, fields_json from create_event"))
    c.close()
    by_creator = collections.defaultdict(list)
    for slot, tx, bc, creator, _m, _cb, _f in rows:
        by_creator[creator].append((slot, tx, bc))
    for v in by_creator.values():
        v.sort()
    rank = {}
    for creator, lst in by_creator.items():
        for k, (_s, _t, bc) in enumerate(lst):
            rank[bc] = (k, len(lst))

    feats = {}
    for slot, tx, bc, creator, mayhem, cashback, fields_json in rows:
        host = None
        try:
            uri = (json.loads(fields_json) or {}).get("uri") or ""
            if "://" in uri:
                host = uri.split("://", 1)[1].split("/", 1)[0].lower()
        except Exception:
            host = None
        pr, tot = rank.get(bc, (0, 1))
        feats[bc] = {
            "prior_launches": pr,
            "creator_launches_in_window": tot,
            "uri_host": host,
            "is_mayhem_mode": mayhem,
            "is_cashback_enabled": cashback,
        }
    _log("window creates: %d rows, %d distinct creators" % (len(rows), len(by_creator)))
    return feats


# --------------------------------------------------------------------------
# stage 5 -- failed-transaction census (zero RPC, never previously used)
# --------------------------------------------------------------------------
def failed_tx_features(signatures_db: str, curves: dict, t0_by_curve: dict) -> dict:
    s = _ro(signatures_db)
    out = {bc: {"fail10": 0, "fail60": 0, "fail_total": 0,
                "ok10": 0, "ok60": 0} for bc in curves}
    n = 0
    for bc, bt, err in s.execute(
        "select bonding_curve, block_time, err_json from signature_observation"
    ):
        rec = out.get(bc)
        if rec is None:
            continue
        n += 1
        failed = err is not None and err != "null"
        if failed:
            rec["fail_total"] += 1
        t0 = t0_by_curve.get(bc)
        if t0 is None or bt is None:
            continue
        if bt <= t0 + 10:
            rec["fail10" if failed else "ok10"] += 1
        if bt <= t0 + MINUTE:
            rec["fail60" if failed else "ok60"] += 1
    s.close()
    _log("signature census: %d in-cohort signature rows scanned" % n)
    return out


# --------------------------------------------------------------------------
# stage 6 -- real holder concentration at t0+60s from postTokenBalances
# --------------------------------------------------------------------------
def holder_concentration(bodies_db: str, curves: dict, slot_time: dict,
                         t0_by_curve: dict) -> dict:
    """Replay absolute post-balances in (slot, transaction_index) order and keep
    each owner's last known balance at or before t0+60s."""
    mint_to_bc = {c["mint"]: bc for bc, c in curves.items()}
    curve_addr = set(curves)
    balances = collections.defaultdict(dict)   # bc -> owner -> raw amount
    b = _ro(bodies_db)
    q = ("select tc.slot, tc.transaction_index, rt.raw_zlib"
         " from transaction_coordinate tc join raw_transaction rt"
         "   on rt.signature = tc.signature"
         " order by tc.slot, tc.transaction_index")
    seen = used = 0
    t_start = time.time()
    for slot, _tx, blob in b.execute(q):
        seen += 1
        if seen % 50000 == 0:
            _log("  bodies %d/%d (%.0fs)" % (seen, 326509, time.time() - t_start))
        bt = slot_time.get(slot)
        try:
            body = json.loads(zlib.decompress(blob))
        except Exception:
            continue
        meta = ((body.get("result") or {}).get("meta") or {})
        ptb = meta.get("postTokenBalances") or []
        if not ptb:
            continue
        touched = False
        for e in ptb:
            bc = mint_to_bc.get(e.get("mint"))
            if bc is None:
                continue
            t0 = t0_by_curve.get(bc)
            if t0 is None or bt is None or bt > t0 + MINUTE:
                continue
            owner = e.get("owner")
            if owner is None or owner in curve_addr:
                continue          # the curve's own ATA holds the unsold supply
            try:
                amt = int((e.get("uiTokenAmount") or {}).get("amount") or 0)
            except (TypeError, ValueError):
                continue
            balances[bc][owner] = amt
            touched = True
        if touched:
            used += 1
    b.close()
    _log("holder snapshot: %d bodies scanned, %d inside a t0+60s window, %.0fs"
         % (seen, used, time.time() - t_start))

    out = {}
    for bc, owners in balances.items():
        held = sorted((v for v in owners.values() if v > 0), reverse=True)
        total = sum(held)
        out[bc] = {
            "n_holders60": len(held),
            "held_tokens60": total,
            "top1_balance_share": (held[0] / total) if total else None,
            "top10_balance_share": (sum(held[:10]) / total) if total else None,
            "held_of_sellable60": total / CURVE_SELLABLE_SUPPLY if total else 0.0,
        }
    return out


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------
COLUMNS = [
    ("bonding_curve", "TEXT PRIMARY KEY"),
    ("mint", "TEXT"),
    ("regime", "TEXT"),
    ("graduated", "INTEGER"),
    ("create_slot", "INTEGER"),
    ("t0_block_time", "INTEGER"),
    # --- price path (the baseline the provenance features must beat) ---
    ("floor_px", "REAL"), ("px60", "REAL"), ("m60", "REAL"), ("m300", "REAL"),
    ("last_px", "REAL"), ("min_px", "REAL"), ("ever_below_floor", "INTEGER"),
    ("n_priced_obs", "INTEGER"),
    # --- provenance: identity ---
    ("creator", "TEXT"), ("create_user", "TEXT"), ("t0_kind", "TEXT"),
    ("prior_launches", "INTEGER"), ("creator_launches_in_window", "INTEGER"),
    ("uri_host", "TEXT"), ("is_mayhem_mode", "INTEGER"),
    ("is_cashback_enabled", "INTEGER"),
    # --- provenance: bundled supply in the create transaction ---
    ("n_bundled_buys", "INTEGER"), ("bundled_share", "REAL"),
    ("bundled_creator_share", "REAL"),
    # --- provenance: sniper share of the first N slots ---
    ("s1_share", "REAL"), ("s1_wallets", "INTEGER"),
    ("s5_share", "REAL"), ("s5_wallets", "INTEGER"),
    ("s20_share", "REAL"), ("s20_wallets", "INTEGER"),
    # --- provenance: minute-1 arrival ---
    ("n_trades60", "INTEGER"), ("n_buys60", "INTEGER"),
    ("uniq_buyers60", "INTEGER"), ("cluster_buyers60", "INTEGER"),
    ("n_trades_total", "INTEGER"),
    # --- provenance: concentration at t0+60s ---
    ("top10_balance_share", "REAL"), ("top1_balance_share", "REAL"),
    ("n_holders60", "INTEGER"), ("held_of_sellable60", "REAL"),
    ("top10_flow_share", "REAL"),          # DEGENERATE -- see module docstring
    ("n_flow_holders60", "INTEGER"),
    # --- provenance: competition intensity (failed transactions) ---
    ("fail10", "INTEGER"), ("fail60", "INTEGER"), ("fail_total", "INTEGER"),
    ("ok10", "INTEGER"), ("ok60", "INTEGER"),
]


def build(cache_path: str, rebuild: bool = False) -> str:
    srcs = {
        "paths": os.path.join(B11A, "b11a_paths.sqlite"),
        "identity": os.path.join(B11A, "b11a_identity.sqlite"),
        "creates": os.path.join(B11A, "b11a_creates.sqlite"),
        "signatures": os.path.join(B11A, "b11a_signatures.sqlite"),
        "bodies": os.path.join(B11A, "b11a_bodies.sqlite"),
    }
    stamp = {"extractor_sha256": _self_sha256(), "sources": _source_stamp(srcs)}

    if os.path.exists(cache_path) and not rebuild:
        try:
            con = sqlite3.connect("file:%s?mode=ro" % cache_path, uri=True)
            got = json.loads(
                con.execute("select value from manifest where key='stamp'").fetchone()[0])
            con.close()
            if got == stamp:
                _log("cache is current: %s" % cache_path)
                return cache_path
            _log("cache stamp differs -> rebuilding")
        except Exception:
            _log("cache unreadable -> rebuilding")

    t_all = time.time()
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)

    curves = load_curves(srcs["paths"], srcs["identity"])
    _log("curves: %d, graduated: %d" % (len(curves), sum(c["graduated"] for c in curves.values())))

    slot_time, slot_disagree = load_slot_times(srcs["signatures"], srcs["creates"])
    t0_by_curve = {bc: slot_time.get(c["create_slot"]) for bc, c in curves.items()}
    _log("t0 known for %d/%d curves" % (sum(1 for v in t0_by_curve.values() if v is not None), len(curves)))

    price = price_features(srcs["paths"], curves, slot_time)
    _log("price features: %d curves" % len(price))

    win = window_features(srcs["creates"])

    # --- trades, grouped per curve ---
    _log("scanning instructions + reserves ...")
    t = time.time()
    trades = collections.defaultdict(list)
    n_act = n_noamt = 0
    name_counts = collections.Counter()
    for slot, tx, outer, inner, name, side, bc, wallet, tokens in load_actions(srcs["bodies"]):
        n_act += 1
        name_counts[name] += 1
        if side == 0 or bc not in curves:
            continue
        if tokens is None:
            n_noamt += 1
            continue
        trades[bc].append((slot, tx, outer, inner, side, wallet, tokens, slot_time.get(slot)))
    for v in trades.values():
        v.sort()
    _log("actions: %d rows (%d trades without a reserve delta), %d curves with >=1 trade, %.0fs"
         % (n_act, n_noamt, len(trades), time.time() - t))
    _log("instruction mix: %s" % dict(name_counts))

    creators = {c["creator"] for c in curves.values() if c["creator"]}

    fails = failed_tx_features(srcs["signatures"], curves, t0_by_curve)
    holders = holder_concentration(srcs["bodies"], curves, slot_time, t0_by_curve)

    rows = []
    for bc, c in curves.items():
        pf = price.get(bc, {})
        wf = win.get(bc, {})
        ff = fails.get(bc, {})
        hf = holders.get(bc, {})
        tr = trades.get(bc, [])
        cs, ct, cr = c["create_slot"], c["create_tx"], c["creator"]
        t0 = t0_by_curve.get(bc)

        bundled = [x for x in tr if x[0] == cs and x[1] == ct and x[4] > 0]
        bundled_tok = sum(x[6] for x in bundled)
        bundled_creator = sum(x[6] for x in bundled if x[5] == cr)

        def sniper(nslots):
            w = [x for x in tr if x[0] <= cs + nslots and x[4] > 0]
            return sum(x[6] for x in w), len({x[5] for x in w})

        s1, s5, s20 = (sniper(n) for n in SNIPER_SLOT_WINDOWS)

        w60 = [x for x in tr if t0 is not None and x[7] is not None and x[7] <= t0 + MINUTE]
        b60 = [x for x in w60 if x[4] > 0]
        uniq60 = len({x[5] for x in b60})
        cluster60 = len({x[5] for x in b60 if x[5] in creators and x[5] != cr})

        pos = collections.defaultdict(int)
        for x in w60:
            pos[x[5]] += x[6] if x[4] > 0 else -x[6]
        flow_held = sorted((v for v in pos.values() if v > 0), reverse=True)
        flow_tot = sum(flow_held)

        rows.append((
            bc, c["mint"], c["regime"], c["graduated"], cs, t0,
            pf.get("floor_px"), pf.get("px60"), pf.get("m60"), pf.get("m300"),
            pf.get("last_px"), pf.get("min_px"), pf.get("ever_below_floor"),
            pf.get("n_priced_obs"),
            cr, c["create_user"], c["t0_kind"],
            wf.get("prior_launches"), wf.get("creator_launches_in_window"),
            wf.get("uri_host"), wf.get("is_mayhem_mode"), wf.get("is_cashback_enabled"),
            len(bundled), bundled_tok / CURVE_SELLABLE_SUPPLY,
            bundled_creator / CURVE_SELLABLE_SUPPLY,
            s1[0] / CURVE_SELLABLE_SUPPLY, s1[1],
            s5[0] / CURVE_SELLABLE_SUPPLY, s5[1],
            s20[0] / CURVE_SELLABLE_SUPPLY, s20[1],
            len(w60), len(b60), uniq60, cluster60, len(tr),
            hf.get("top10_balance_share"), hf.get("top1_balance_share"),
            hf.get("n_holders60"), hf.get("held_of_sellable60"),
            (sum(flow_held[:10]) / flow_tot) if flow_tot > 0 else None,
            len(flow_held),
            ff.get("fail10"), ff.get("fail60"), ff.get("fail_total"),
            ff.get("ok10"), ff.get("ok60"),
        ))

    tmp = cache_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    out = sqlite3.connect(tmp)
    out.execute("create table features (%s)" %
                ", ".join("%s %s" % (n, t) for n, t in COLUMNS))
    out.executemany("insert into features values (%s)" % ",".join("?" * len(COLUMNS)), rows)
    out.execute("create index features_m60 on features(m60)")
    out.execute("create table manifest (key TEXT PRIMARY KEY, value TEXT)")
    out.execute("insert into manifest values ('stamp', ?)", (json.dumps(stamp, sort_keys=True),))
    out.execute("insert into manifest values ('built_unix', ?)", (json.dumps(time.time()),))
    out.execute("insert into manifest values ('slot_time_disagreements', ?)",
                (json.dumps(slot_disagree),))
    out.execute("insert into manifest values ('n_rows', ?)", (json.dumps(len(rows)),))
    out.commit()
    out.close()
    os.replace(tmp, cache_path)
    _log("wrote %d rows -> %s (%.0fs total)" % (len(rows), cache_path, time.time() - t_all))
    return cache_path


# --------------------------------------------------------------------------
# selftest -- arithmetic identities that must hold, or the extract is wrong
# --------------------------------------------------------------------------
def selftest(cache_path: str) -> int:
    con = sqlite3.connect("file:%s?mode=ro" % cache_path, uri=True)
    q = con.execute
    fails = []

    def check(label, ok, detail=""):
        print("  %-62s %s %s" % (label, "PASS" if ok else "FAIL", detail))
        if not ok:
            fails.append(label)

    n, g = q("select count(*), sum(graduated) from features").fetchone()
    check("row count == 3932", n == 3932, "n=%d" % n)
    check("graduation label count == 82", g == 82, "g=%d" % g)

    below = q("select sum(ever_below_floor) from features").fetchone()[0]
    check("no curve ever traded below its floor price", below == 0, "below=%s" % below)

    nullcr = q("select count(*) from features where creator is null").fetchone()[0]
    check("creator non-null on every curve", nullcr == 0, "null=%d" % nullcr)

    # t0_kind is derived independently upstream; it must agree with our own
    # same-transaction-buy indicator to the unit.
    a = q("select count(*) from features where t0_kind='TradeEvent'").fetchone()[0]
    b = q("select count(*) from features where n_bundled_buys > 0").fetchone()[0]
    check("t0_kind=TradeEvent == n_bundled_buys>0", a == b, "%d vs %d" % (a, b))

    bad = q("select count(*) from features where bundled_share > 1.0001").fetchone()[0]
    check("bundled_share <= 1", bad == 0, "violations=%d" % bad)

    mono = q("select count(*) from features where s1_share > s5_share + 1e-12"
             " or s5_share > s20_share + 1e-12").fetchone()[0]
    check("sniper share monotone in slot window", mono == 0, "violations=%d" % mono)

    bad = q("select count(*) from features where top10_balance_share is not null"
            " and (top10_balance_share < 0 or top10_balance_share > 1.0000001)").fetchone()[0]
    check("top10_balance_share in [0,1]", bad == 0, "violations=%d" % bad)

    bad = q("select count(*) from features where n_holders60 <= 10"
            " and abs(top10_balance_share - 1.0) > 1e-9").fetchone()[0]
    check("top10 share == 1 when holders <= 10", bad == 0, "violations=%d" % bad)

    mfloor = q("select min(m60) from features where m60 is not null").fetchone()[0]
    check("min entry premium m60 >= 1", mfloor >= 1 - 1e-9, "min=%.9f" % mfloor)

    # the degenerate column must be visibly degenerate
    deg, tot = q("select sum(top10_flow_share > 0.9999), count(top10_flow_share)"
                 " from features").fetchone()
    print("  NOTE  top10_flow_share == 1.0 for %d of %d defined -> degenerate, unusable"
          % (deg, tot))
    con.close()
    print("\n  %d/%d checks failed" % (len(fails), 11))
    return 1 if fails else 0


def summarise(cache_path: str) -> None:
    con = sqlite3.connect("file:%s?mode=ro" % cache_path, uri=True)
    q = con.execute
    print("\n=== provenance_features cache: %s ===" % cache_path)
    n, g = q("select count(*), sum(graduated) from features").fetchone()
    print("rows=%d graduated=%d base_rate=%.4f%%" % (n, g, 100.0 * g / n))
    print("\ncolumn coverage (non-null / %d) and graduate coverage (of %d):" % (n, g))
    for name, _t in COLUMNS:
        c, gc = q("select count(%s), sum(case when %s is not null then graduated else 0 end)"
                  " from features" % (name, name)).fetchone()
        print("  %-26s %6d  %5.1f%%   grads %2d" % (name, c, 100.0 * c / n, gc or 0))
    con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--cache", default=DEFAULT_CACHE)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    path = build(a.cache, rebuild=a.rebuild)
    rc = 0
    if a.selftest:
        print("\n=== provenance_features selftest ===")
        rc = selftest(path)
    if a.summary:
        summarise(path)
    return rc


if __name__ == "__main__":
    sys.exit(main())
