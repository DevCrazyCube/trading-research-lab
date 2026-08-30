#!/usr/bin/env python3
"""Hostile controls for the PAC V2.3 PumpSwap sell-quote and pool observer.

Every number here is checked against the chain-verified reference decode of mainnet pool
4LjdwBex5xRBvf63KioUagLX4g3UzQhEqj8wJRm3Mr3T (2026-08-30). No network: the provider is driven by a
canned opener so failure classification (bounded PumpSwapUnavailable vs hard RefusedExecution) is
tested deterministically.
"""
from __future__ import annotations

import base64
import io
import json
import pathlib
import tempfile
import struct

from .execution import PriceUnavailable, RefusedExecution
from . import pac_v2_pumpswap as ps


CHECKS = 0


def check(condition: bool, label: str) -> None:
    global CHECKS
    if not condition:
        raise AssertionError(label)
    CHECKS += 1
    print(f"[ok] {label}")


def refuses(exc_type, fn, label: str) -> None:
    try:
        fn()
    except exc_type:
        check(True, label)
    else:
        raise AssertionError(label)


WSOL = ps.WSOL_MINT
MINT = "FSQgP6a26KFEDrpsJJfSLnkWiy59ScKY2EChEGU9pump"


def _pool_bytes(base_mint: str, quote_mint: str, base_vault: str, quote_vault: str) -> bytes:
    raw = bytearray(ps._POOL_MIN_LEN + 40)
    raw[:8] = ps._POOL_DISCRIMINATOR
    raw[ps._POOL_BASE_MINT_OFF:ps._POOL_BASE_MINT_OFF + 32] = ps._b58decode(base_mint)
    raw[ps._POOL_QUOTE_MINT_OFF:ps._POOL_QUOTE_MINT_OFF + 32] = ps._b58decode(quote_mint)
    raw[ps._POOL_BASE_VAULT_OFF:ps._POOL_BASE_VAULT_OFF + 32] = ps._b58decode(base_vault)
    raw[ps._POOL_QUOTE_VAULT_OFF:ps._POOL_QUOTE_VAULT_OFF + 32] = ps._b58decode(quote_vault)
    return bytes(raw)


def _token_bytes(mint: str, amount: int) -> bytes:
    raw = bytearray(165)
    raw[ps._TOKEN_MINT_OFF:ps._TOKEN_MINT_OFF + 32] = ps._b58decode(mint)
    struct.pack_into("<Q", raw, ps._TOKEN_AMOUNT_OFF, amount)
    return bytes(raw)


def _config_bytes(lp: int, protocol: int, creator: int) -> bytes:
    raw = bytearray(ps._GLOBAL_MIN_LEN + 8)
    struct.pack_into("<Q", raw, ps._GLOBAL_LP_FEE_OFF, lp)
    struct.pack_into("<Q", raw, ps._GLOBAL_PROTOCOL_FEE_OFF, protocol)
    struct.pack_into("<Q", raw, ps._GLOBAL_CREATOR_FEE_OFF, creator)
    return bytes(raw)


def _b64(raw: bytes) -> list:
    return [base64.b64encode(raw).decode(), "base64"]


class _Response(io.BytesIO):
    def __init__(self, payload: dict, status: int = 200):
        super().__init__(json.dumps(payload).encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def make_opener(*, pools: list, vault_accounts: list, status: int = 200):
    def opener(request, timeout=None):
        body = json.loads(request.data)
        if body["method"] == "getProgramAccounts":
            return _Response({"jsonrpc": "2.0", "id": body["id"], "result": pools}, status)
        if body["method"] == "getMultipleAccounts":
            return _Response({"jsonrpc": "2.0", "id": body["id"],
                              "result": {"context": {"slot": 442_976_000}, "value": vault_accounts}},
                             status)
        raise AssertionError("unexpected RPC method")
    return opener


def main() -> int:
    _tmp = pathlib.Path(tempfile.mkdtemp()) / "pumpswap_exchanges.jsonl"
    # 1. Chain-verified reference quote is reproduced to the lamport.
    ref = ps.PumpSwapReserves(base_reserve=181_247_007_803_288, quote_reserve=79_586_527_324,
                              lp_fee_bps=20, protocol_fee_bps=5, creator_fee_bps=5)
    q = ps.sell_quote(1_000_000_000, ref)
    check(q["gross_quote_lamports"] == 439_102 and q["net_quote_lamports"] == 437_783,
          "chain-verified reference sell quote reproduces gross 439102 / net 437783")

    # 2. Fees are charged on the output and rounded UP (ceilDiv), never truncated to zero.
    tiny = ps.PumpSwapReserves(1_000_000, 1_000_000, 20, 5, 5)
    tq = ps.sell_quote(10_000, tiny)
    check(tq["lp_fee_lamports"] >= 1 and tq["net_quote_lamports"] < tq["gross_quote_lamports"],
          "each fee is charged on the gross output and rounded up")

    # 3. Non-positive quotes and inputs fail closed as a named venue inability, never a zero fill.
    refuses(PriceUnavailable, lambda: ps.sell_quote(0, ref), "zero token input refuses to price")
    refuses(PriceUnavailable, lambda: ps.sell_quote(-5, ref), "negative token input refuses to price")
    refuses(PriceUnavailable, lambda: ps.sell_quote(1, ps.PumpSwapReserves(10**18, 1, 20, 5, 5)),
            "a dust-thin pool that prices zero lamports out refuses")

    # 4. Reserve/fee validation: positive reserves and a bounded fee regime.
    refuses(RefusedExecution, lambda: ps.PumpSwapReserves(0, 1, 0, 0, 0),
            "non-positive base reserve refuses")
    refuses(RefusedExecution, lambda: ps.PumpSwapReserves(1, 1, 600, 0, 0),
            "a fee regime above the supported bound refuses rather than misprices")

    # 5. base58 encodes the all-zero pubkey as exactly 32 ones (no 33rd sentinel char), roundtrips.
    check(ps._b58encode(bytes(32)) == "1" * 32, "all-zero pubkey encodes to exactly 32 base58 ones")
    check(ps._b58decode(ps._b58encode(ps._b58decode(WSOL))) == ps._b58decode(WSOL),
          "base58 pubkey roundtrips")

    # 6. Pool layout decode extracts the two vaults and enforces base-mint / WSOL-quote identity.
    pool = _pool_bytes(MINT, WSOL, MINT, WSOL)  # vault pubkeys are placeholders here
    bv, qv = ps._decode_pool(pool, mint=MINT)
    check(bv == MINT and qv == WSOL, "pool decode returns the base and quote vault pubkeys")
    refuses(RefusedExecution, lambda: ps._decode_pool(_pool_bytes(WSOL, WSOL, MINT, WSOL), mint=MINT),
            "a pool whose base mint is not the requested mint refuses")
    refuses(RefusedExecution, lambda: ps._decode_pool(_pool_bytes(MINT, MINT, MINT, MINT), mint=MINT),
            "a non-WSOL-quoted pool refuses")

    # 7. End-to-end capture happy path: discover one pool, read both vaults + live fees, quote.
    base_vault, quote_vault = "7a8nQKdWdPSHFqp49ruPJhwkSxcXbitbbAuyDMZndDg5", \
        "EDfnWYYeGDzr7EcHPQYtuxFGKWAe2V9MyNUwKCSuUe6j"
    pool_pubkey = "4LjdwBex5xRBvf63KioUagLX4g3UzQhEqj8wJRm3Mr3T"
    pool_ok = [{"pubkey": pool_pubkey,
                "account": {"owner": ps.PUMPSWAP_PROGRAM,
                            "data": _b64(_pool_bytes(MINT, WSOL, base_vault, quote_vault))}}]
    vaults_ok = [
        {"owner": ps._TOKEN_PROGRAM, "data": _b64(_token_bytes(MINT, 356_486_832_936_467))},
        {"owner": ps._TOKEN_PROGRAM, "data": _b64(_token_bytes(WSOL, 31_987_155_272))},
        {"owner": "anyprogram", "data": _b64(_config_bytes(20, 5, 5))},
    ]
    prov = ps.PumpSwapProvider(exchange_path=_tmp,
                               opener=make_opener(pools=pool_ok, vault_accounts=vaults_ok))
    obs = prov.capture(MINT, minimum_context_slot=0)
    check(obs.pool == pool_pubkey and obs.reserves.base_reserve == 356_486_832_936_467
          and obs.reserves.quote_reserve == 31_987_155_272 and obs.reserves.total_fee_bps == 30,
          "capture discovers the pool, reads both vault reserves and the live 30bps fee regime")

    # 8. No pool for the mint is a BOUNDED reason to keep holding, not a hard refusal.
    empty = ps.PumpSwapProvider(exchange_path=_tmp,
                                opener=make_opener(pools=[], vault_accounts=[]))
    refuses(ps.PumpSwapUnavailable, lambda: empty.capture(MINT, 0),
            "a mint with no PumpSwap pool raises the bounded PumpSwapUnavailable")

    # 9. Multiple pools is an ambiguous venue -> hard refusal, never a silent pick.
    two = ps.PumpSwapProvider(exchange_path=_tmp,
                              opener=make_opener(pools=pool_ok * 2, vault_accounts=vaults_ok))
    refuses(RefusedExecution, lambda: two.capture(MINT, 0),
            "an ambiguous multi-pool discovery refuses rather than guessing a venue")

    # 10. A vault holding the wrong mint is a hard layout refusal.
    wrong = ps.PumpSwapProvider(
        exchange_path=_tmp,
        opener=make_opener(pools=pool_ok, vault_accounts=[
            {"owner": ps._TOKEN_PROGRAM, "data": _b64(_token_bytes(WSOL, 1))},  # base vault wrong mint
            vaults_ok[1], vaults_ok[2]]))
    refuses(RefusedExecution, lambda: wrong.capture(MINT, 0),
            "a vault holding the wrong mint refuses")

    # 11. A missing GlobalConfig account is bounded, not an unclassified crash (review MEDIUM).
    noconfig = ps.PumpSwapProvider(
        exchange_path=_tmp,
        opener=make_opener(pools=pool_ok, vault_accounts=[vaults_ok[0], vaults_ok[1], None]))
    refuses(ps.PumpSwapUnavailable, lambda: noconfig.capture(MINT, 0),
            "a null GlobalConfig account raises bounded PumpSwapUnavailable, not AttributeError")

    # 12. Transport non-200 is bounded (keep holding), never a fill.
    down = ps.PumpSwapProvider(exchange_path=_tmp,
                               opener=make_opener(pools=pool_ok, vault_accounts=vaults_ok, status=503))
    refuses(ps.PumpSwapUnavailable, lambda: down.capture(MINT, 0),
            "an RPC 503 raises the bounded PumpSwapUnavailable")

    print(f"\nPAC V2.3 PumpSwap selftest: {CHECKS} hostile checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
