#!/usr/bin/env python3
"""Shared, dependency-light helpers for the DataProvider layer (PAPER / READ-ONLY).

Nothing here signs, sends, loads a wallet, or reads a private key. It only reads market data and
the .env for endpoint URLs / API tokens, and it never prints a secret.

It also re-uses the audited JSON-RPC request identity from ``scripts/rpc_http_identity.py`` (loaded
by absolute path, the established idiom in this repo) so every RPC call this layer makes carries the
same WAF-safe, credential-free ``User-Agent`` and the same 403-is-terminal retry classification the
B11 pipeline already relies on.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import pathlib
import struct
import sys
import urllib.error
import urllib.request
from typing import Optional

# ---- locate the repo and the sibling contract / shared helper --------------------------------
_HERE = pathlib.Path(__file__).resolve()
# data/_common.py -> data -> sniper -> trading_bot -> scripts -> <repo root>
SCRIPTS_DIR = _HERE.parents[3]
REPO_ROOT = _HERE.parents[4]
ENV_PATH = REPO_ROOT / ".env"
CACHE_DIR = REPO_ROOT / "research" / "data" / "memebot_cache" / "bitquery_candles"


def _load_by_path(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass/typing machinery can resolve the module by name.
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


# The audited JSON-RPC request identity (fixed non-identifying User-Agent, 403-terminal retry rules).
HTTP = _load_by_path("rpc_http_identity", SCRIPTS_DIR / "rpc_http_identity.py")

# The shared contract. Loaded by path so every provider module shares ONE types instance and the
# dataclasses compare identically, no matter how the package is invoked.
_TYPES = _load_by_path("sniper_types", _HERE.parents[1] / "types.py")
TokenEvent = _TYPES.TokenEvent
TradeTick = _TYPES.TradeTick
Bar = _TYPES.Bar

# Wrapped SOL / system mints treated as the "cash" leg, never the traded memecoin (mirrors
# scripts/smartmoney/collect_trades.py).
SOL_MINTS = {
    "11111111111111111111111111111111",
    "So11111111111111111111111111111111111111112",
}

# ---- pump.fun on-chain program identity + TradeEvent layout ----------------------------------
# The bonding-curve program. Its `emit!(TradeEvent)` surfaces in transaction logs as a
# `Program data: <base64>` line (Solana `sol_log_data`), so the live WS path can decode a trade
# straight from the log payload with no per-tx getTransaction round-trip.
PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
# The migrated-AMM program (pump_amm / "Pumpswap"). Its Buy/Sell events use a DIFFERENT layout;
# decoding them is a documented extension seam, not implemented here (see ChainstackProvider).
PUMPSWAP_PROGRAM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"

# Anchor event discriminator for TradeEvent = sha256("event:TradeEvent")[:8], as pinned in
# research/pump_idl_9c82f61.json (events[].discriminator for "TradeEvent"). Verified against the
# live WS feed on 2026-08-26.
_TRADE_EVENT_DISCRIMINATOR = bytes([189, 219, 127, 211, 78, 230, 97, 238])

# pump.fun mints are SPL tokens with 6 decimals; SOL/lamports carry 9. Reserves are raw integer
# units, so the price ratio must correct for the 3-decimal gap.
_TOKEN_DECIMALS = 6
_SOL_DECIMALS = 9
_DECIMAL_ADJ = 10 ** (_SOL_DECIMALS - _TOKEN_DECIMALS)  # 1e3

# SOL/USD used to turn lamport amounts + the SOL-denominated bonding-curve price into USD. The WS
# feed carries no fiat rate, so this is a single recent constant. TODO(price): refresh from a cheap
# quote source (or a periodic getAccountInfo on a Pyth/oracle account) instead of a pinned literal.
SOL_USD_DEFAULT = 200.0

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(raw: bytes) -> str:
    """Base58 (Bitcoin/Solana alphabet) encode raw pubkey bytes to a mint/address string."""
    n = int.from_bytes(raw, "big")
    out = ""
    while n > 0:
        n, rem = divmod(n, 58)
        out = _B58_ALPHABET[rem] + out
    pad = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * pad + (out or "1")


def decode_pump_trade_event(payload: bytes, sol_usd: float = SOL_USD_DEFAULT) -> Optional[dict]:
    """Decode ONE pump.fun `Program data:` payload into a normalized trade dict, or None.

    Returns None unless the payload is a TradeEvent (matched by its 8-byte Anchor discriminator).
    Only the leading, fixed-offset fields needed for a tick are read (mint, sol/token amounts,
    is_buy, user, timestamp, and the two virtual reserves); the many trailing fields — including the
    variable-length `ix_name`/`shareholders` — are intentionally left undecoded.

    Price derivation: the marginal bonding-curve price is virtual_sol_reserves / virtual_token_
    reserves (decimal-corrected), quoted in SOL, then multiplied by `sol_usd`. Trade USD size is the
    lamport `sol_amount` converted to SOL then to USD. Mirrors the reserve-ratio pricing already used
    in scripts/trading_bot/memestream/sources.py::normalize_pumpportal_trade.
    """
    if len(payload) < 8 or payload[:8] != _TRADE_EVENT_DISCRIMINATOR:
        return None
    body = payload[8:]
    off = 0

    def take(width: int) -> bytes:
        nonlocal off
        chunk = body[off:off + width]
        off += width
        return chunk

    try:
        mint = b58encode(take(32))
        sol_amount = struct.unpack_from("<Q", take(8))[0]
        token_amount = struct.unpack_from("<Q", take(8))[0]
        is_buy = take(1)[0] != 0
        user = b58encode(take(32))
        ts = struct.unpack_from("<q", take(8))[0]
        # The four u64s after `ts` are [intervening field, virtual_token, real_sol, real_token] -- the
        # first is NOT virtual_sol (verified live: reading it as virtual_sol gave < 30 SOL, breaking the
        # constant-product invariant). The exact virtual reserves are recovered from the REAL reserves +
        # the pinned launch offsets (virtual = real + offset; verified: virtual_token - real_token =
        # 279_900_000_000_000 atoms, and virtual_sol - real_sol = 30_000_000_000 lamports).
        _intervening = struct.unpack_from("<Q", take(8))[0]
        virtual_tok = struct.unpack_from("<Q", take(8))[0]
        real_sol = struct.unpack_from("<Q", take(8))[0]
        real_tok = struct.unpack_from("<Q", take(8))[0]
        virtual_sol = real_sol + 30_000_000_000
    except (struct.error, IndexError):
        return None
    if virtual_tok <= 0:
        return None
    price_sol = (virtual_sol / virtual_tok) / _DECIMAL_ADJ
    price_usd = price_sol * sol_usd
    usd = (sol_amount / (10 ** _SOL_DECIMALS)) * sol_usd
    return {"mint": mint, "ts": int(ts), "price_usd": price_usd, "usd": usd,
            "side": "buy" if is_buy else "sell", "user": user, "venue": "Pumpfun",
            # Raw curve state + amounts, so consumers that need the exact reserves (the AFTERSHOCK tape /
            # ECR engine) get them without re-decoding. virtual_sol is LAMPORTS, virtual_tok is ATOMS,
            # sol_amount is LAMPORTS, token_amount is ATOMS. Existing tick consumers ignore these keys.
            "virtual_sol": virtual_sol, "virtual_tok": virtual_tok,
            "real_sol": real_sol, "real_tok": real_tok,
            "sol_amount": sol_amount, "token_amount": token_amount}


def decode_pump_trades_from_logs(logs, sol_usd: float = SOL_USD_DEFAULT) -> list:
    """Decode every TradeEvent carried in a transaction's log list. Non-trade lines are ignored."""
    out = []
    for line in logs or []:
        if not isinstance(line, str) or not line.startswith("Program data:"):
            continue
        try:
            payload = base64.b64decode(line.split("Program data:", 1)[1].strip())
        except (ValueError, base64.binascii.Error):
            continue
        ev = decode_pump_trade_event(payload, sol_usd)
        if ev is not None:
            out.append(ev)
    return out


# ---- read 1s bars straight off the on-disk memebot_cache -------------------------------------
def load_cached_bars(mint: str, cache_dir: pathlib.Path = CACHE_DIR) -> list:
    """Load all on-disk 1s Bars for a mint from research/data/memebot_cache/bitquery_candles/."""
    path = pathlib.Path(cache_dir) / f"{mint}.jsonl"
    if not path.exists():
        return []
    bars = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            bars.append(Bar(t=int(d["t"]), o=float(d["o"]), h=float(d["h"]), l=float(d["l"]),
                            c=float(d["c"]), v=float(d.get("v", 0.0)),
                            buys=int(d.get("buys", 0)), sells=int(d.get("sells", 0)),
                            buy_vol=float(d.get("buy_vol", 0.0)), sell_vol=float(d.get("sell_vol", 0.0)),
                            dex=d.get("dex")))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            continue
    bars.sort(key=lambda b: b.t)
    return bars


class RefusedError(RuntimeError):
    """A provider refused to serve data (403 / plan inactive / quota exhausted). Terminal.

    Raised (rather than returned empty) where a caller asked a live provider to do real work and the
    provider is entitled to nothing. The runner treats a Refused as "fall back to the next provider".
    """


# ---- .env reading, WITHOUT ever printing a secret --------------------------------------------
def read_env(key: str, path: pathlib.Path = ENV_PATH) -> Optional[str]:
    """Return the value of ``key`` from the repo .env, or None. Never logs or returns nothing but
    the value itself; callers must not print it."""
    try:
        text = pathlib.Path(path).read_text()
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            v = v.strip().strip('"').strip("'")
            return v or None
    return None


# ---- one JSON-RPC POST, using the audited request identity -----------------------------------
def rpc_call(url: str, method: str, params=None, timeout: float = 10.0):
    """POST a single JSON-RPC 2.0 call and return its ``result``.

    Raises ``RefusedError`` on a 403 (Cloudflare 1010 / plan inactive) or a JSON-RPC ``error``
    object (e.g. Chainstack ``-32002`` plan-entitlement). Transport faults propagate as urllib
    errors for the caller to classify. Never prints the URL (it may embed a key in its path)."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params if params is not None else []}).encode()
    req = HTTP.json_rpc_request(url, body)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if HTTP.is_client_refusal(exc.code):
            raise RefusedError(f"{method} refused: HTTP {exc.code} (plan inactive / WAF)") from exc
        raise
    if isinstance(data, dict) and data.get("error"):
        raise RefusedError(f"{method} error: {data['error']}")
    return data.get("result") if isinstance(data, dict) else data


# ---- build 1s OHLCV+flow bars from a flat trade list -----------------------------------------
def trades_to_bars(trades) -> list:
    """Bucket priced trades (dicts with ts/price_usd/usd/side, optional dex) into 1-second Bars.

    Matches the on-disk memebot_cache candle schema exactly. Trades with a non-positive price carry
    no usable quote and are skipped for OHLC.
    """
    buckets: dict[int, dict] = {}
    for tr in sorted(trades, key=lambda x: x["ts"]):
        p = float(tr.get("price_usd") or 0.0)
        if p <= 0:
            continue
        sec = int(tr["ts"])
        u = float(tr.get("usd") or 0.0)
        side = tr.get("side")
        b = buckets.get(sec)
        if b is None:
            b = {"t": sec, "o": p, "h": p, "l": p, "c": p, "v": 0.0,
                 "buys": 0, "sells": 0, "buy_vol": 0.0, "sell_vol": 0.0, "dex": tr.get("dex")}
            buckets[sec] = b
        b["h"] = max(b["h"], p)
        b["l"] = min(b["l"], p)
        b["c"] = p
        b["v"] += u
        if side == "buy":
            b["buys"] += 1
            b["buy_vol"] += u
        elif side == "sell":
            b["sells"] += 1
            b["sell_vol"] += u
    return [Bar(t=b["t"], o=b["o"], h=b["h"], l=b["l"], c=b["c"], v=b["v"],
                buys=b["buys"], sells=b["sells"], buy_vol=b["buy_vol"], sell_vol=b["sell_vol"],
                dex=b["dex"]) for _, b in sorted(buckets.items())]
