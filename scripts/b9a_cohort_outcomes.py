#!/usr/bin/env python3
"""B9a — the first outcome measurement: graduation base rate for the B8b cohort.

Everything before this measured the instrument. This measures what actually happened.

The B8b window was pinned to end **8.000 days before tip**, so its observation period is already
complete and the labels `W_obs` was defined to permit are available now. `BondingCurve` carries
`complete: bool` — the graduation flag — and `real_quote_reserves`, which says how far a curve got.
`getMultipleAccounts` batches 100, so the whole 1,601-member cohort costs ~17 requests.

**This is a label, not a feature.** Current account state read ≥8 days after launch is exactly the
end-of-observation outcome. Using it as a model input would be leakage of the most direct kind, and
the artifact is named `outcome` throughout so that misuse has to be deliberate.

Rules frozen in `agent_discussion.md` before the first request (Seq 176):

* the whole cohort is reported, then split by frozen covariates — never filtered;
* a **missing** bonding-curve account is its own category, never folded into graduated or not —
  it may mean closed-after-migration, and assuming so is the convenient inference;
* no strategy, no return, no model — a base rate only.

Read-only. No signing, no spending, no transactions. Credentials come from SOLANA_RPC_URL and are
never printed or persisted.
"""
import argparse
import base64
import json
import os
import sqlite3
import struct
import time
import urllib.error
import urllib.request

BATCH = 100                     # getMultipleAccounts limit
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SOL_SENTINEL = "11111111111111111111111111111111"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# BondingCurve, in IDL order after the 8-byte Anchor discriminator.
#   virtual_token_reserves u64 · virtual_quote_reserves u64 · real_token_reserves u64
#   real_quote_reserves u64 · token_total_supply u64 · complete bool · creator pubkey
#   is_mayhem_mode bool · is_cashback_coin bool · quote_mint pubkey
CURVE_STRUCT = struct.Struct("<QQQQQ?")
CURVE_PREFIX = 8


def rpc(url, method, params, retries=6):
    body = json.dumps({"jsonrpc": "2.0", "id": 1,
                       "method": method, "params": params}).encode()
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.load(response)
            if "error" in payload:
                raise RuntimeError(payload["error"].get("message", "rpc error"))
            return payload["result"]
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            if attempt == retries - 1:
                raise
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError("unreachable")


def decode_curve(account):
    """`None` when the account is absent; a dict otherwise.

    Absence is returned distinctly rather than as a falsy curve, because "no account" and "a curve
    that never completed" are different outcomes and the freeze requires them reported apart.
    """
    if account is None:
        return None
    raw = base64.b64decode(account["data"][0])
    if len(raw) < CURVE_PREFIX + CURVE_STRUCT.size:
        raise ValueError(f"bonding curve account too short: {len(raw)} bytes")
    fields = CURVE_STRUCT.unpack_from(raw, CURVE_PREFIX)
    return {
        "virtual_token_reserves": fields[0], "virtual_quote_reserves": fields[1],
        "real_token_reserves": fields[2], "real_quote_reserves": fields[3],
        "token_total_supply": fields[4], "complete": fields[5],
        "owner": account.get("owner"), "lamports": account.get("lamports"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort",
                        default="research/b8b_cohort_433894233_434097833.sqlite")
    parser.add_argument("--database", default="research/b9a_outcomes.sqlite")
    parser.add_argument("--retries", type=int, default=6)
    arguments = parser.parse_args()

    url = os.environ.get("SOLANA_RPC_URL")
    if not url:
        raise SystemExit("REFUSING: SOLANA_RPC_URL is not set. Source .env silently first.")

    source = sqlite3.connect(f"file:{arguments.cohort}?mode=ro", uri=True)
    members = source.execute(
        "SELECT mint, bonding_curve, creator, user, is_mayhem_mode, quote_mint, slot "
        "FROM create_event ORDER BY slot, transaction_index").fetchall()
    cohort_meta = dict(source.execute("SELECT key, value FROM metadata"))
    source.close()
    print(f"cohort members: {len(members):,}  (from {arguments.cohort})")

    out = sqlite3.connect(arguments.database)
    out.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outcome (
            mint TEXT PRIMARY KEY, bonding_curve TEXT NOT NULL, creator TEXT, user TEXT,
            is_mayhem_mode INTEGER, quote_mint TEXT, launch_slot INTEGER,
            account_present INTEGER NOT NULL, complete INTEGER,
            real_quote_reserves INTEGER, real_token_reserves INTEGER,
            virtual_quote_reserves INTEGER, virtual_token_reserves INTEGER,
            token_total_supply INTEGER, owner TEXT, lamports INTEGER,
            observed_at_unix REAL NOT NULL
        );
    """)
    out.executemany("INSERT OR REPLACE INTO metadata VALUES (?, ?)", [
        ("cohort_artifact", arguments.cohort),
        ("cohort_window_start", cohort_meta.get("window_start_slot", "")),
        ("cohort_window_end", cohort_meta.get("window_end_slot_inclusive", "")),
        ("cohort_freeze_sha256", cohort_meta.get("freeze_sha256", "")),
        ("measurement", "BondingCurve.complete at end of observation (label, NOT a feature)"),
        ("endpoint_ref", "public-mainnet" if "api.mainnet-beta" in url else "configured-mainnet"),
    ])
    out.commit()

    done = {row[0] for row in out.execute("SELECT mint FROM outcome")}
    pending = [m for m in members if m[0] not in done]
    print(f"already measured: {len(done):,}   pending: {len(pending):,}")

    for start in range(0, len(pending), BATCH):
        chunk = pending[start:start + BATCH]
        result = rpc(url, "getMultipleAccounts",
                     [[row[1] for row in chunk],
                      {"encoding": "base64", "commitment": "finalized"}],
                     arguments.retries)
        accounts = result["value"]
        if len(accounts) != len(chunk):
            raise SystemExit(f"REFUSING: asked for {len(chunk)} accounts, got {len(accounts)}")
        rows = []
        for (mint, curve, creator, user, mayhem, quote, slot), account in zip(chunk, accounts):
            decoded = decode_curve(account)
            rows.append((
                mint, curve, creator, user, mayhem, quote, slot,
                1 if decoded else 0,
                (1 if decoded["complete"] else 0) if decoded else None,
                decoded["real_quote_reserves"] if decoded else None,
                decoded["real_token_reserves"] if decoded else None,
                decoded["virtual_quote_reserves"] if decoded else None,
                decoded["virtual_token_reserves"] if decoded else None,
                decoded["token_total_supply"] if decoded else None,
                decoded["owner"] if decoded else None,
                decoded["lamports"] if decoded else None,
                time.time(),
            ))
        with out:
            out.executemany(
                "INSERT OR REPLACE INTO outcome VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        print(f"  {min(start + BATCH, len(pending)):,}/{len(pending):,}", flush=True)

    total = out.execute("SELECT COUNT(*) FROM outcome").fetchone()[0]
    if total != len(members):
        print(f"\nRESULT: **INCOMPLETE** — {total:,} of {len(members):,} measured.")
        out.close()
        return 1
    print(f"\nRESULT: **COMPLETE** — {total:,} members measured.")
    out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
