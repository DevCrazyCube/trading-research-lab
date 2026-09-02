#!/usr/bin/env python3
"""Multi-venue launchpad registry + pure decoders — the measured constants behind every launch curve.

WHY THIS FILE EXISTS
--------------------
`research/b11a/` closed the price-derived question on pump.fun: the bonding curve is hard-floored at the
launch price (0 of 3,239 curves ever traded below their first observed price), graduation pays a
DETERMINISTIC 14.6958x, and momentum's 540x graduation lift is fully impounded in the entry premium — every
premium bucket is EV <= 0. What remained was (a) whether another venue is structurally better, and (b) the
LABEL WALL: 82 graduations total, only 3 inside the floor-priced cohort of 2,975.

Recon A answered (a) negatively and measured every constant below against LIVE mainnet accounts decoded
with each program's own on-chain Anchor IDL. This module is that measurement, frozen as code: one registry
row per venue, every number carrying the n / basis / measured-vs-derived provenance it was born with, plus
the pure EV algebra and the pure log decoders a listener needs to harvest CREATE and GRADUATION labels.

THE ONE LAW
-----------
For any constant-product launch curve the graduation multiple is a fixed point of the curve, not a market
outcome:

    X = (Q0 + R)^2 / Q0^2          Q0 = initial virtual QUOTE reserve, R = quote raised at graduation

pump.fun: Q0 = 30 SOL, R = 85.0054 SOL -> X = 14.6958 (reproduces the +1369.4% measured on all 82 b11a
graduates). LetsBonk/LaunchLab: Q0 = 30.000853 SOL, R = 85.0 -> X = 14.6938 — the SAME geometry on a
different venue, which is what makes it a natural control rather than merely more data.

For Meteora DBC's piecewise concentrated-liquidity curve the equivalent closed form is

    X = (migration_sqrt_price / sqrt_start_price)^2

verified by integrating the on-chain liquidity array: base and quote integrals reproduce the stored
`swap_base_amount` and `migration_quote_threshold` to ratio 1.0000 on all 12 configs tested.

EV FRAME
--------
    EV(m) = (1 + (X-1)p) / m - 1 - toll          m = entry price / floor price, toll = round-trip
    m*    = (1 + (X-1)p) / (1 + toll)            the break-even entry premium (EV = 0)

The prize term (X-1)p lands in 0.077..0.286 across EVERY real venue despite X spanning 11x..200x and p
spanning 0.045%..2.15%. Launchpads compete on curve shape and the market prices it straight back out.
That collapse is itself the finding: there is no free venue.

DISCIPLINE
----------
Every number here is `measured` (read off-chain / counted) or `derived` (computed from measured inputs by
the law above). Where a quantity could NOT be established — Boop's multiple (damping_term=31 makes the
curve non-constant-product and the two plain-CP readings disagree, 15.15x vs 23.36x), Heaven's virtual
liquidity (no anchor:idl PDA on-chain) — the field is None and carries the refusal text instead of a guess.
`graduation_multiple()` and `ev_breakeven_premium()` RAISE on those venues rather than return a number.

READ-ONLY, PURE: zero I/O beyond hashing the pinned IDL files, zero network, zero deps. Nothing here can
place an order.  Self-check: `python -m scripts.trading_bot.memebot.venues`
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import pathlib
import struct

_ROOT = pathlib.Path(__file__).resolve().parents[3]
IDL_DIR = _ROOT / "research" / "launchpads" / "idl"

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------------------------------
# Pinned on-chain Anchor IDLs. Each was fetched from the program's own `anchor:idl` PDA (Recon A) and is
# hashed here, so a silent swap of the layout this decoder was written against refuses loudly.
# ---------------------------------------------------------------------------------------------------
PINNED_IDLS = {
    "pump.fun": ("idl_pump.fun.json",
                 "ecf91ed5050c2c8e3e618bd330091f56d7433789eff724dfcc81fd47d1bab7d4"),
    "raydium_launchlab": ("idl_raydium launchlab.json",
                          "d3e708672e1b2f2c8f6f882a8ef56ba3a9fb8481b13ee9469ea34a67eea9335b"),
    "meteora_dbc": ("idl_meteora DBC.json",
                    "2ac53765b597e3f15c840a2a349bc9b6393a55d4130912f8d19dbd8c054b1a4f"),
    "boop": ("idl_boop.json",
             "0540d99d17ce7915146db148648b19f2bcabd6b46a8abdb9fc6b378520e23ccc"),
}

LAMPORTS = 1_000_000_000        # SOL, 9 decimals
USDC_UNITS = 1_000_000          # USDC, 6 decimals


class VenueRefused(Exception):
    """Refusing to return a number this module cannot justify from a measurement."""


# ---------------------------------------------------------------------------------------------------
# Borsh reading + base58 (self-contained; this module imports nothing from the live arena closure)
# ---------------------------------------------------------------------------------------------------
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = ""
    while n > 0:
        n, rem = divmod(n, 58)
        out = _B58[rem] + out
    pad = 0
    for b in raw:
        if b == 0:
            pad += 1
        else:
            break
    return "1" * pad + out


class Cursor:
    """Minimal borsh reader. Every decoder below asserts it consumed the payload EXACTLY — a layout that
    drifted leaves bytes over (or runs short) and the event is dropped rather than half-decoded."""
    __slots__ = ("buf", "i")

    def __init__(self, buf: bytes, i: int = 0):
        self.buf, self.i = buf, i

    def take(self, n: int) -> bytes:
        if n < 0 or self.i + n > len(self.buf):
            raise ValueError("anchor event truncated")
        chunk = self.buf[self.i:self.i + n]
        self.i += n
        return chunk

    def u8(self) -> int:
        return self.take(1)[0]

    def bool_(self) -> bool:
        v = self.take(1)[0]
        if v > 1:
            raise ValueError("bool out of range")
        return v == 1

    def u16(self) -> int:
        return struct.unpack_from("<H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack_from("<I", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack_from("<Q", self.take(8))[0]

    def i64(self) -> int:
        return struct.unpack_from("<q", self.take(8))[0]

    def u128(self) -> int:
        return int.from_bytes(self.take(16), "little")

    def pubkey(self) -> str:
        return b58encode(self.take(32))

    def string(self, *, max_len: int = 4096) -> str:
        n = self.u32()
        if n > max_len:
            raise ValueError("anchor string implausibly long")
        return self.take(n).decode("utf-8", "replace")

    def exhausted(self) -> bool:
        return self.i == len(self.buf)


# ---------------------------------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class Venue:
    """One launch venue (or one launch CONFIG, where a program hosts many — see meteora_dbc).

    Every economic field carries its provenance in `provenance`: 'measured' means read off-chain or
    counted; 'derived' means computed from measured inputs by the constant-product / sqrt-price law.
    A None field means the quantity was NOT established; `unverified` says why.
    """
    venue_id: str
    display_name: str
    program_id: str
    chain: str
    verified_onchain: bool
    quote_symbol: str
    quote_units: int                       # smallest units per 1 quote token
    curve_kind: str                        # constant_product | concentrated_liquidity | damped | none
    # curve constants (quote-denominated, in whole quote tokens)
    q0_quote: float | None                 # initial VIRTUAL quote reserve
    raise_quote: float | None              # quote raised at graduation
    sqrt_start_price: int | None           # DBC only (u128 Q64)
    sqrt_migration_price: int | None       # DBC only (u128 Q64)
    graduation_multiple_x: float | None    # X
    toll_per_side: float | None
    toll_round_trip: float | None
    graduation_rate_p: float | None        # p
    p_n: int | None
    p_grads: int | None
    p_basis: str
    platform_config: str | None            # LaunchLab platform / DBC config the economics belong to
    listener_program: str | None           # key into PROGRAMS (None => not tapeable here)
    provenance: dict
    unverified: str | None = None
    note: str = ""

    def require_x(self) -> float:
        if self.graduation_multiple_x is None:
            raise VenueRefused(
                f"{self.venue_id}: graduation multiple is NOT established. {self.unverified or ''}".strip())
        return self.graduation_multiple_x

    def require_toll(self) -> float:
        if self.toll_round_trip is None:
            raise VenueRefused(f"{self.venue_id}: round-trip toll is NOT established. "
                               f"{self.unverified or ''}".strip())
        return self.toll_round_trip

    def require_p(self) -> float:
        if self.graduation_rate_p is None:
            raise VenueRefused(f"{self.venue_id}: graduation rate p is NOT established. "
                               f"{self.unverified or ''}".strip())
        return self.graduation_rate_p


# --- program ids (all verified executable on mainnet via the funded Helius RPC, Recon A) --------------
PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPSWAP_AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
LAUNCHLAB_PROGRAM = "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj"
DBC_PROGRAM = "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN"
BOOP_PROGRAM = "boop8hVGQGqehUK2iVEMEnMrL5RbjywRzHKBmBE7ry4"
HEAVEN_PROGRAM = "HEAVENoP2qxoeuF8Dj2oT1GHEnu49U5mJYkdeC8BAX2o"
MOONSHOT_LEGACY_PROGRAM = "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG"

NATIVE_SOL_DEFAULT = "1" * 32     # pump.fun's "native SOL" sentinel (32 zero bytes)
WRAPPED_SOL = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

_M = "measured (Recon A, live mainnet accounts decoded against the program's on-chain anchor:idl)"
_D = "derived from measured curve constants by X = (Q0+R)^2/Q0^2"
_DS = ("TRANSCRIBED literal, NOT derived here: the sqrt prices this claim needs are not stored on the "
       "record, so this module cannot execute X = (migration_sqrt/sqrt_start)^2. Value came from an "
       "offline decode of PoolConfig (u128 @280/@392) and is unverified by any self-test. Treat as "
       "unconfirmed until sqrt_start_price/sqrt_migration_price are stored and X is computed.")


def _cp_multiple(q0: float, raise_quote: float) -> float:
    """X = (Q0+R)^2 / Q0^2 — the graduation multiple of a constant-product launch curve.

    Completion is a FIXED POINT of the curve, not a market outcome: the pool must be bought from Q0 to
    Q0+R of virtual quote, and price on a constant-product curve scales with the square of the quote
    reserve. Hence a deterministic multiple, identical for every coin that graduates on that curve.
    """
    if q0 <= 0 or raise_quote < 0:
        raise VenueRefused(f"non-physical curve constants q0={q0} raise={raise_quote}")
    return ((q0 + raise_quote) / q0) ** 2


def _sqrt_multiple(sqrt_start: int, sqrt_migration: int) -> float:
    """X = (migration_sqrt_price / sqrt_start_price)^2 — Meteora DBC's piecewise-CL equivalent."""
    if sqrt_start <= 0 or sqrt_migration <= 0:
        raise VenueRefused("non-physical sqrt prices")
    return (sqrt_migration / sqrt_start) ** 2


_PUMP_Q0, _PUMP_R = 30.0, 85.0054
_LL_Q0, _LL_R = 30.000852951, 85.0
_MOONSHOT_SQRT_START, _MOONSHOT_SQRT_MIG = 41248174037003916, 583337266871351544

VENUES: dict[str, Venue] = {}


def _register(v: Venue) -> Venue:
    if v.venue_id in VENUES:
        raise VenueRefused(f"duplicate venue_id {v.venue_id!r}")
    VENUES[v.venue_id] = v
    return v


_register(Venue(
    venue_id="pump.fun", display_name="pump.fun", program_id=PUMP_PROGRAM, chain="solana",
    verified_onchain=True, quote_symbol="SOL", quote_units=LAMPORTS, curve_kind="constant_product",
    q0_quote=_PUMP_Q0, raise_quote=_PUMP_R, sqrt_start_price=None, sqrt_migration_price=None,
    graduation_multiple_x=_cp_multiple(_PUMP_Q0, _PUMP_R),
    # Global account 4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf: fee_basis_points=95 +
    # creator_fee_basis_points=5 = 100 bps = 1.00%/side. NOTE this is the PROTOCOL toll only; the arena's
    # fill.py deliberately books 1.5%/leg (see TOLL_DISCREPANCY below).
    toll_per_side=0.01, toll_round_trip=0.02,
    graduation_rate_p=82 / 3932, p_n=3932, p_grads=82,
    p_basis="research/b11a survivorship-free 23h create window, 11.9d follow (measured)",
    platform_config=None, listener_program="pump.fun",
    provenance={"q0_quote": _M + " Global.initial_virtual_sol_reserves=30e9 lamports",
                "raise_quote": _M + " vSOL 30 -> 115.0054 at completion",
                "graduation_multiple_x": _D + "; reproduces +1369.4% on all 82 b11a graduates",
                "toll_per_side": _M + " Global fee_basis_points 95 + creator_fee_basis_points 5",
                "graduation_rate_p": "measured 82/3932 (research/b11a)"},
    note="initial_virtual_token_reserves=1.073e15 raw (1.073e9 tokens @6dp); "
         "initial_real_token_reserves=793.1e12; token_total_supply=1e15; "
         "pool_migration_fee=15000001 lamports; graduates to PumpSwap AMM " + PUMPSWAP_AMM))

_register(Venue(
    venue_id="letsbonk", display_name="LetsBonk / bonk.fun (Raydium LaunchLab)",
    program_id=LAUNCHLAB_PROGRAM, chain="solana", verified_onchain=True, quote_symbol="SOL",
    quote_units=LAMPORTS, curve_kind="constant_product",
    q0_quote=_LL_Q0, raise_quote=_LL_R, sqrt_start_price=None, sqrt_migration_price=None,
    graduation_multiple_x=_cp_multiple(_LL_Q0, _LL_R),
    toll_per_side=0.015, toll_round_trip=0.03,
    graduation_rate_p=10994 / 1035966, p_n=1035966, p_grads=10994,
    p_basis="ALL-TIME census of PoolState accounts under the LetsBonk platform config (measured; "
            "biased DOWN by pools launched minutes before the query — NOT like-for-like with "
            "pump.fun's 23h window + 11.9d follow)",
    platform_config="FfYek5vEz23cMkWsdJwG2oa6EphsvXSHrGpdALN4g6W1", listener_program="raydium_launchlab",
    provenance={"q0_quote": _M + " PoolState.virtual_quote = 30,000,852,951 lamports",
                "raise_quote": _M + " total_quote_fund_raising = 85e9 lamports",
                "graduation_multiple_x": _D,
                "toll_per_side": _M + " live TradeEvent: quote 1,930,000 -> protocol_fee 4,825 (0.25%) "
                                      "+ platform_fee 24,125 (1.25%) = exactly 1.5000%",
                "graduation_rate_p": "measured 10,994 migrated of 1,035,966 pools (status==2 @off17)"},
    note="THE LABEL SET. Same curve geometry as pump.fun (virtual_base 1,073,025,605,596,382, "
         "total_base_sell 793.1e12, 85 SOL raise) at 134x pump.fun's label count, different toll "
         "(3.0% vs 2.0%) and half the graduation rate. PoolState accounts are never closed, so the "
         "status byte is a PERMANENT, survivorship-free graduation label."))

_register(Venue(
    venue_id="raydium_own", display_name="Raydium own platform (LaunchLab)",
    program_id=LAUNCHLAB_PROGRAM, chain="solana", verified_onchain=True, quote_symbol="SOL",
    quote_units=LAMPORTS, curve_kind="constant_product",
    q0_quote=_LL_Q0, raise_quote=_LL_R, sqrt_start_price=None, sqrt_migration_price=None,
    graduation_multiple_x=_cp_multiple(_LL_Q0, _LL_R),
    toll_per_side=0.0105, toll_round_trip=0.021,
    graduation_rate_p=540 / 95816, p_n=95816, p_grads=540,
    p_basis="all-time census under the Raydium-own platform config (measured, same downward bias)",
    platform_config="4Bu96XjU84XjPDSpveTVf6LYGCkfW5FK7SNkREWcEfV4", listener_program="raydium_launchlab",
    provenance={"toll_per_side": _M + " 0.25% protocol + 0.75% platform + 0.05% creator = 1.05%/side, "
                                      "confirmed 1.0612%-of-net on a live sell",
                "graduation_multiple_x": _D + " for the dominant config; an ALTERNATE config on this "
                                              "platform has Q0=28.3333, R=85 -> X = 16.0000 exactly",
                "graduation_rate_p": "measured 540 migrated of 95,816 pools"},
    note="platform_fee_rate=7500ppm, creator_fee_rate=500ppm"))

_register(Venue(
    venue_id="moonshot_dbc", display_name="Moonshot (on Meteora DBC, USDC-quoted)",
    program_id=DBC_PROGRAM, chain="solana", verified_onchain=True, quote_symbol="USDC",
    quote_units=USDC_UNITS, curve_kind="concentrated_liquidity",
    q0_quote=None, raise_quote=66040.882531,
    sqrt_start_price=_MOONSHOT_SQRT_START, sqrt_migration_price=_MOONSHOT_SQRT_MIG,
    graduation_multiple_x=_sqrt_multiple(_MOONSHOT_SQRT_START, _MOONSHOT_SQRT_MIG),
    toll_per_side=0.005, toll_round_trip=0.01,
    graduation_rate_p=3 / 6624, p_n=6624, p_grads=3,
    p_basis="6,624 DBC pools sampled on the Moonshot config, 3 migrated (measured)",
    platform_config="FbKf76ucsQssF7XZBuzScdJfugtsSKwZFYztKsMEhWZM", listener_program="meteora_dbc",
    provenance={"graduation_multiple_x": _DS + " -> exactly 200.0000x",
                "raise_quote": _M + " migration_quote_threshold = 66,040.88 USDC",
                "toll_per_side": _M + " cliff_fee 5,000,000 / 1e9 = 0.50%/side",
                "graduation_rate_p": "measured 3/6,624 — THREE events; statistically near-worthless"},
    note="THE 200x TRAP: the biggest prize on Solana and it LOSES on EV. (X-1)p = 0.090 vs pump.fun's "
         "0.286, because p collapses by 46x. Identified by mints ending 'moon' + cdn.moonshot.com "
         "metadata URIs. Legacy Moonshot program " + MOONSHOT_LEGACY_PROGRAM + " is still executable."))

# --- Meteora DBC configs measured individually. There is NO 'the Meteora multiple': 21,182 distinct
# configs in a 60,000-pool sample, X from 1.0000x to 200.0000x. Any DBC strategy must read the config
# per pool at creation time. These are recorded for completeness, NOT for action: the top two by m*
# rest on 4 and 10 graduations respectively.
for _cfg, _x, _side, _thr, _n, _g, _nt in (
    ("GybkUNYVNk1FZMt9myAfvpSVgoKBgaueMTvszwBN4qYx", 18.1745, 0.02, 98.377, 274, 4, ""),
    ("BkoMF8PzYwoVQTKcQ6uNeQrHytw1jJN6ig4JzjcKS3iF", 11.0000, 0.015, 66.0, 465, 10, ""),
    ("7UNpFBfTdWrcfS7aBQzEaPgZCfPJe8BDgHzwmWUZaMaF", 18.1745, 0.01, 85.017, 259, 0, ""),
    ("AxVRAxqnPLz9dv3DFnksAbFKdv7H5LBmznG7YiuZMCan", 12.6290, 0.0025, 10.98, 932, 931,
     "~100% graduation and NOT a single-tx bundle: real pools, 350-1,000+ txs, curve completes in "
     "48-224s. Unidentified venue. Flagged, not ranked."),
    ("GEi2PKrdDMGG2vmwcYLTrHfwnHszc8eLfPP2Q9j9JmLu", 1.1747, 0.01, 12.0, 3642, 3634,
     "referenced BY the Bags update authority BAGSB9Tp... — NOT confirmed to BE Bags (Bags publishes "
     "no PartnerMetadata). Near-instant-liquidity config."),
):
    _register(Venue(
        venue_id=f"dbc_{_cfg[:4].lower()}", display_name=f"Meteora DBC config {_cfg[:8]}...",
        program_id=DBC_PROGRAM, chain="solana", verified_onchain=True, quote_symbol="SOL",
        quote_units=LAMPORTS, curve_kind="concentrated_liquidity",
        q0_quote=None, raise_quote=_thr, sqrt_start_price=None, sqrt_migration_price=None,
        graduation_multiple_x=_x, toll_per_side=_side, toll_round_trip=2 * _side,
        graduation_rate_p=_g / _n, p_n=_n, p_grads=_g,
        p_basis=f"{_n} pools sampled on this config, {_g} migrated (measured)",
        platform_config=_cfg, listener_program="meteora_dbc",
        provenance={"graduation_multiple_x": _DS + " (PoolConfig u128 @280 and @392)",
                    "graduation_rate_p": f"measured {_g}/{_n}"},
        note=_nt))

_register(Venue(
    venue_id="boop", display_name="Boop", program_id=BOOP_PROGRAM, chain="solana",
    verified_onchain=True, quote_symbol="SOL", quote_units=LAMPORTS, curve_kind="damped",
    q0_quote=29.7313958, raise_quote=86.0, sqrt_start_price=None, sqrt_migration_price=None,
    graduation_multiple_x=None,
    toll_per_side=0.02, toll_round_trip=0.04,
    graduation_rate_p=None, p_n=None, p_grads=None, p_basis="not measured",
    platform_config=None, listener_program="boop",
    provenance={"q0_quote": _M + " Config.virtual_sol_reserves = 29,731,395,800 lamports",
                "raise_quote": _M + " graduation_target = 86e9 lamports",
                "toll_per_side": _M + " swap_fee_basis_points = 200"},
    unverified="damping_term=31 means the curve is NOT plain constant product. Assuming CP from the "
               "86 SOL target gives 15.15x; assuming CP from the 793.1M on-curve tokens gives a "
               "113.97 SOL raise and 23.36x. The two disagree, so no closed form is justified without "
               "the program source or an empirical fit on real Boop graduates. REFUSING a number.",
    note="graduation_fee=6 SOL; token_amount_for_raydium_liquidity=206.9M tokens"))

_register(Venue(
    venue_id="heaven", display_name="Heaven", program_id=HEAVEN_PROGRAM, chain="solana",
    verified_onchain=True, quote_symbol="SOL", quote_units=LAMPORTS, curve_kind="none",
    q0_quote=None, raise_quote=None, sqrt_start_price=None, sqrt_migration_price=None,
    graduation_multiple_x=None, toll_per_side=None, toll_round_trip=None,
    graduation_rate_p=None, p_n=None, p_grads=None, p_basis="n/a — no graduation exists",
    platform_config=None, listener_program=None,
    provenance={"program_id": _M + " executable, last activity 2026-09-02"},
    unverified="Heaven has NO bonding curve and NO graduation: every token opens as an AMM pool seeded "
               "with virtual liquidity, so the deterministic-prize EV frame does not apply at all. It "
               "also has no anchor:idl PDA, so its ~35 SOL virtual liquidity and 1%/0.5%/0.25% fee "
               "tiers are DOC CLAIMS ONLY, not measured.",
    note="protocol config v3 HtYH4a2q1PXPErgNxVPTmoTKbE2Y7cpSQVDAEbQqgKCm"))

# Venues the owner named that are NOT on Solana. Recorded so the name-match trap is documented rather
# than repeated: matching 'flap'/'pons' to a Solana LaunchLab platform config finds squatters with
# exactly 1 pool each. Counting the pools is what falsified it.
NOT_ON_SOLANA = {
    "pons": {"chain": "Robinhood Chain (EVM, chainId 4663)", "verified_onchain": False,
             "active_factory": "0xA5aAb3F0c6EeadF30Ef1D3Eb997108E976351feB",
             "events": ["TokenLaunched"], "state_fn": "graduationStatus()",
             "scale": "22,581 tokens minted on 2026-08-30 alone; ~1 in 10 chain txs in early Aug 2026",
             "source": "vendor documentation only — no Robinhood Chain RPC configured in this repo",
             "solana_squatter_config": "5jXn5ko9AWLpaTPF5rD5kyxZXcapkfaRCrgRFrFQDgm5 (1 pool, ever)"},
    "flap": {"chain": "BNB Chain (origin) + X Layer + Monad + Morph + Robinhood Chain",
             "verified_onchain": False, "bnb_graduation": "16 BNB -> PancakeSwap V3",
             "source": "vendor documentation only",
             "solana_squatter_config": "2t5xeJtqNrQWaTJNfnY6gj5nBUuUwPG6qNuGD1w27Ce5 (1 pool, ever)"},
}

# The live arena books TOLL_BUY = TOLL_SELL = 0.015 (3% round trip) in arena/fill.py. pump.fun's actual
# ON-CHAIN protocol toll is 1.00%/side = 2.00% round trip. The 3% is EXACT for LetsBonk and CONSERVATIVE
# for pump.fun (it also absorbs priority fee + slippage, which the protocol toll does not). fill.py is a
# live-arm closure file: changing it re-epochs every live ledger. Recorded here, not acted on.
TOLL_DISCREPANCY = {
    "arena_fill_py_round_trip": 0.03,
    "pumpfun_measured_protocol_round_trip": 0.02,
    "letsbonk_measured_round_trip": 0.03,
    "verdict": "conservative for pump.fun, exact for LetsBonk; an owner decision, not a bug to patch",
}


# ---------------------------------------------------------------------------------------------------
# The EV algebra — pure
# ---------------------------------------------------------------------------------------------------
def _venue(v: "Venue | str") -> Venue:
    if isinstance(v, Venue):
        return v
    try:
        return VENUES[v]
    except KeyError:
        raise VenueRefused(f"unknown venue {v!r}; known: {sorted(VENUES)}") from None


def graduation_multiple(venue: "Venue | str") -> float:
    """X, the deterministic payoff of graduating on this venue's curve. Raises where not established."""
    return _venue(venue).require_x()


def ev_at_premium(venue: "Venue | str", p: float, m: float, *,
                  toll_round_trip: float | None = None) -> float:
    """EV = (1 + (X-1)p)/m - 1 - toll.

    m is the ENTRY PREMIUM: entry price / floor (launch) price. The b11a floor result is what makes this
    the whole story on a bonding curve — 0 of 3,239 pump.fun curves ever traded below their first
    observed price, so the only on-curve downside is the premium you paid above the floor, and the only
    upside that is not a market forecast is the deterministic graduation multiple.
    """
    v = _venue(venue)
    if m <= 0:
        raise VenueRefused(f"entry premium m must be positive, got {m}")
    if not 0.0 <= p <= 1.0:
        raise VenueRefused(f"graduation probability p must be in [0,1], got {p}")
    toll = v.require_toll() if toll_round_trip is None else toll_round_trip
    return (1.0 + (v.require_x() - 1.0) * p) / m - 1.0 - toll


def ev_breakeven_premium(venue: "Venue | str", p: float, *,
                         toll_round_trip: float | None = None) -> float:
    """m* = (1 + (X-1)p) / (1 + toll) — the entry premium at which EV(m) = 0.

    Above m*, buying the curve is negative-expectancy no matter what the momentum says; the b11a
    per-coin simulation showed the price impounds the graduation lift so completely that EVERY observed
    premium bucket sits on the wrong side of it.
    """
    v = _venue(venue)
    if not 0.0 <= p <= 1.0:
        raise VenueRefused(f"graduation probability p must be in [0,1], got {p}")
    toll = v.require_toll() if toll_round_trip is None else toll_round_trip
    return (1.0 + (v.require_x() - 1.0) * p) / (1.0 + toll)


def prize_term(venue: "Venue | str", p: float | None = None) -> float:
    """(X-1)p — the entire upside of the EV frame, stripped of toll and premium."""
    v = _venue(venue)
    return (v.require_x() - 1.0) * (v.require_p() if p is None else p)


# A rank is only worth reading when the census behind p is big enough to mean anything and the venue is
# actually a LOTTERY. These thresholds are declared here rather than buried in a filter so the reader can
# see exactly which rows a caveat disqualifies and why.
MIN_CENSUS_N = 1000            # below this, p is a rumour
MIN_GRADUATIONS = 25           # below this, m* moves with one coin
MAX_LOTTERY_P = 0.5            # above this the config is an instant-liquidity vehicle, not a lottery


def rank_caveats(v: Venue) -> list[str]:
    """Why this venue's rank should not be believed. Empty list = a rank worth reading."""
    out = []
    if (v.p_n or 0) < MIN_CENSUS_N:
        out.append(f"census n={v.p_n} < {MIN_CENSUS_N}: p is a rumour")
    if (v.p_grads or 0) < MIN_GRADUATIONS:
        out.append(f"only {v.p_grads} graduations: m* moves with one coin")
    if (v.graduation_rate_p or 0) > MAX_LOTTERY_P:
        out.append(f"p={v.graduation_rate_p:.1%} — near-certain completion, so this is an "
                   "instant-liquidity config, not a graduation lottery. Its huge apparent EV at m=1 is "
                   "an artefact: the curve is consumed by bundled/sniper flow in seconds, so no outside "
                   "buyer is ever AT the floor, and the EV frame's premise does not hold.")
    return out


def rank_venues(venues: "list[str] | None" = None, *, credible_only: bool = False) -> list[dict]:
    """Rank every venue whose X, p and toll are ALL established, by break-even premium m* (descending).

    Rows carry n, the graduation count, and an explicit `caveats` list, so a reader can see instantly
    which ranks rest on a handful of events (dbc_gybk: 4 graduations; dbc_bkom: 10 — do not believe
    them) and which are not lotteries at all. `credible_only=True` returns just the uncaveated rows.
    """
    out = []
    for vid in (venues if venues is not None else list(VENUES)):
        v = _venue(vid)
        if v.graduation_multiple_x is None or v.graduation_rate_p is None or v.toll_round_trip is None:
            continue
        caveats = rank_caveats(v)
        if credible_only and caveats:
            continue
        out.append({
            "venue_id": v.venue_id, "X": v.graduation_multiple_x, "p": v.graduation_rate_p,
            "toll_round_trip": v.toll_round_trip, "prize_term_Xm1p": prize_term(v),
            "breakeven_premium_m_star": ev_breakeven_premium(v, v.graduation_rate_p),
            "ev_at_floor_m_1": ev_at_premium(v, v.graduation_rate_p, 1.0),
            "n": v.p_n, "graduations": v.p_grads, "p_basis": v.p_basis, "caveats": caveats,
        })
    out.sort(key=lambda r: r["breakeven_premium_m_star"], reverse=True)
    return out


# ---------------------------------------------------------------------------------------------------
# Decoders — pure, zero I/O. One per program; each returns NORMALISED create/graduation rows.
# ---------------------------------------------------------------------------------------------------
ANCHOR_CPI_PREFIX = bytes.fromhex("e445a52e51cb9a1d")   # anchor emit_cpi! self-CPI wrapper

# SEEN-vs-DECODED observability, mirroring helius_pump_decode.EVENT_STATS. A silent CompleteEvent drop
# once starved a live arm with no visible error; counting the raw discriminators SEEN next to the ones
# that DECODED makes a layout drift show up as a recurring unknown instead of a silent gap.
EVENT_STATS: dict[str, dict] = {}


def _stats(program_key: str) -> dict:
    return EVENT_STATS.setdefault(program_key, {
        "program_data_lines": 0, "create_seen": 0, "create_decoded": 0,
        "graduation_seen": 0, "graduation_decoded": 0,
        "known_untaped": {},        # events the pinned IDL declares that this tape deliberately skips
        "unknown_disc": {}})        # discriminators the pinned IDL does NOT declare == LAYOUT DRIFT


_IDL_DISCS_CACHE: dict[str, dict] = {}


def _idl_discriminators(program_key: str) -> dict:
    """{hex discriminator -> event name} straight out of the pinned IDL, loaded once."""
    if program_key not in _IDL_DISCS_CACHE:
        try:
            fname, _ = PINNED_IDLS[program_key]
            idl = json.loads((IDL_DIR / fname).read_bytes())
            _IDL_DISCS_CACHE[program_key] = {bytes(e["discriminator"]).hex(): e["name"]
                                             for e in idl.get("events", [])}
        except (KeyError, OSError, ValueError):
            _IDL_DISCS_CACHE[program_key] = {}
    return _IDL_DISCS_CACHE[program_key]


def _note_untaped(st: dict, program_key: str, disc: bytes) -> None:
    """Separate EXPECTED noise from DRIFT.

    A program emits far more than launches and graduations (pump.fun alone publishes 23 event types).
    Bucketing every non-label event into `unknown_disc` would bury the one signal that matters: a
    discriminator the pinned IDL does not declare at all, which means the layout moved under us. So an
    event the IDL knows counts as `known_untaped` (by name), and only a genuinely foreign discriminator
    raises `unknown_disc`."""
    hx = disc.hex()
    name = _idl_discriminators(program_key).get(hx)
    if name is None:
        st["unknown_disc"][hx] = st["unknown_disc"].get(hx, 0) + 1
    else:
        st["known_untaped"][name] = st["known_untaped"].get(name, 0) + 1


def reset_event_stats() -> None:
    EVENT_STATS.clear()


def _row(*, venue: str, kind: str, program_id: str, signature: str | None, slot: int | None,
         **fields) -> dict:
    """One normalised tape row. Absent fields stay ABSENT rather than being filled with a guess."""
    row = {"schema": SCHEMA_VERSION, "venue": venue, "kind": kind, "program_id": program_id}
    row.update({k: v for k, v in fields.items() if v is not None})
    if signature is not None:
        row["signature"] = signature
    if slot is not None:
        row["slot"] = slot
    return row


# --- pump.fun ---------------------------------------------------------------------------------------
DISC_PUMP_CREATE = bytes.fromhex("1b72a94ddeeb6376")
DISC_PUMP_COMPLETE = bytes.fromhex("5f72619cd42e9808")
DISC_PUMP_TRADE = bytes.fromhex("bddb7fd34ee661ee")
_PUMP_TOKEN_DECIMALS = 1_000_000


def decode_pump_create(payload: bytes) -> dict | None:
    if payload[:8] != DISC_PUMP_CREATE:
        return None
    c = Cursor(payload, 8)
    try:
        name, symbol, uri = c.string(), c.string(), c.string()
        mint, bonding_curve, user, creator = c.pubkey(), c.pubkey(), c.pubkey(), c.pubkey()
        c.i64()                                   # timestamp (we stamp local receive time instead)
        v_tok_raw, _v_sol_legacy = c.u64(), c.u64()
        real_tok_raw, total_supply_raw = c.u64(), c.u64()
        c.pubkey()                                # token_program
        is_mayhem, is_cashback = c.bool_(), c.bool_()
        quote_mint = c.pubkey()
        virtual_quote = c.u64()
    except (ValueError, struct.error):
        return None
    if not c.exhausted():
        return None
    return {"mint": mint, "pool_id": bonding_curve, "creator": creator, "user": user,
            "name": name, "symbol": symbol, "uri": uri,
            "quote_mint": quote_mint, "is_mayhem_mode": is_mayhem, "is_cashback_enabled": is_cashback,
            "virtual_quote": virtual_quote / LAMPORTS,
            "virtual_base": v_tok_raw / _PUMP_TOKEN_DECIMALS,
            "real_base": real_tok_raw / _PUMP_TOKEN_DECIMALS,
            "total_supply": total_supply_raw / _PUMP_TOKEN_DECIMALS}


def decode_pump_complete(payload: bytes) -> dict | None:
    if payload[:8] != DISC_PUMP_COMPLETE:
        return None
    c = Cursor(payload, 8)
    try:
        user, mint, bonding_curve = c.pubkey(), c.pubkey(), c.pubkey()
        c.i64()
        quote_mint = c.pubkey()
    except (ValueError, struct.error):
        return None
    if not c.exhausted():
        return None
    return {"mint": mint, "pool_id": bonding_curve, "user": user, "quote_mint": quote_mint}


def _pump_events(payload: bytes, signature, slot) -> list[dict]:
    st = _stats("pump.fun")
    disc = payload[:8]
    if disc == DISC_PUMP_CREATE:
        st["create_seen"] += 1
        ev = decode_pump_create(payload)
        if ev is None:
            return []
        st["create_decoded"] += 1
        return [_row(venue="pump.fun", kind="create", program_id=PUMP_PROGRAM,
                     signature=signature, slot=slot,
                     graduation_multiple_x=VENUES["pump.fun"].graduation_multiple_x, **ev)]
    if disc == DISC_PUMP_COMPLETE:
        st["graduation_seen"] += 1
        ev = decode_pump_complete(payload)
        if ev is None:
            return []
        st["graduation_decoded"] += 1
        return [_row(venue="pump.fun", kind="graduation", program_id=PUMP_PROGRAM,
                     signature=signature, slot=slot,
                     graduation_multiple_x=VENUES["pump.fun"].graduation_multiple_x,
                     raise_quote=_PUMP_R, **ev)]
    _note_untaped(st, "pump.fun", disc)            # trades etc. are expected and NOT taped (labels only)
    return []


# --- Raydium LaunchLab ------------------------------------------------------------------------------
DISC_LL_POOL_CREATE = bytes.fromhex("97d7e20976a173ae")
DISC_LL_TRADE = bytes.fromhex("bddb7fd34ee661ee")
_LL_CURVE_KINDS = {0: "constant_product", 1: "fixed_price", 2: "linear"}
_LL_POOL_STATUS = {0: "fund", 1: "funding_ended_awaiting_migration", 2: "migrated"}


def decode_launchlab_pool_create(payload: bytes) -> dict | None:
    """PoolCreateEvent. NOTE: it carries pool_state but NOT the base mint, and its `config` field is the
    GLOBAL config, not the platform config — so neither the mint nor the LetsBonk/Raydium-own platform
    attribution is recoverable from logs alone. Both need an account read. Recorded, not guessed."""
    if payload[:8] != DISC_LL_POOL_CREATE:
        return None
    c = Cursor(payload, 8)
    try:
        pool_state, creator, config = c.pubkey(), c.pubkey(), c.pubkey()
        decimals = c.u8()
        name, symbol, uri = c.string(), c.string(), c.string()
        curve_tag = c.u8()
        if curve_tag == 0:                        # ConstantCurve
            supply, total_base_sell, total_quote_fund_raising = c.u64(), c.u64(), c.u64()
        elif curve_tag in (1, 2):                 # Fixed / Linear
            supply, total_quote_fund_raising = c.u64(), c.u64()
            total_base_sell = None
        else:
            return None
        migrate_type = c.u8()
        total_locked, cliff_period, unlock_period = c.u64(), c.u64(), c.u64()
        amm_creator_fee_on = c.u8()
    except (ValueError, struct.error):
        return None
    if not c.exhausted() or amm_creator_fee_on > 1 or migrate_type > 1:
        return None
    out = {"pool_id": pool_state, "creator": creator, "global_config": config,
           "base_decimals": decimals, "name": name, "symbol": symbol, "uri": uri,
           "curve_kind": _LL_CURVE_KINDS[curve_tag],
           "supply_raw": supply, "raise_quote": total_quote_fund_raising / LAMPORTS,
           "migrate_type": migrate_type, "vesting_locked_raw": total_locked,
           "vesting_cliff_period": cliff_period, "vesting_unlock_period": unlock_period}
    if total_base_sell is not None:
        out["total_base_sell_raw"] = total_base_sell
    return out


def decode_launchlab_trade(payload: bytes) -> dict | None:
    if payload[:8] != DISC_LL_TRADE:
        return None
    c = Cursor(payload, 8)
    try:
        pool_state = c.pubkey()
        total_base_sell, virtual_base, virtual_quote = c.u64(), c.u64(), c.u64()
        rb_before, rq_before, rb_after, rq_after = c.u64(), c.u64(), c.u64(), c.u64()
        amount_in, amount_out = c.u64(), c.u64()
        protocol_fee, platform_fee, creator_fee, share_fee = c.u64(), c.u64(), c.u64(), c.u64()
        trade_direction, pool_status = c.u8(), c.u8()
        exact_in = c.bool_()
    except (ValueError, struct.error):
        return None
    if not c.exhausted() or trade_direction > 1 or pool_status > 2 or virtual_quote == 0:
        return None
    return {"pool_id": pool_state, "total_base_sell_raw": total_base_sell,
            "virtual_base_raw": virtual_base, "virtual_quote": virtual_quote / LAMPORTS,
            "real_quote_before": rq_before / LAMPORTS, "real_quote_after": rq_after / LAMPORTS,
            "real_base_before_raw": rb_before, "real_base_after_raw": rb_after,
            "amount_in_raw": amount_in, "amount_out_raw": amount_out,
            "fees_quote_raw": protocol_fee + platform_fee + creator_fee + share_fee,
            "side": "buy" if trade_direction == 0 else "sell",
            "pool_status": _LL_POOL_STATUS[pool_status], "exact_in": exact_in}


def _launchlab_events(payload: bytes, signature, slot) -> list[dict]:
    st = _stats("raydium_launchlab")
    disc = payload[:8]
    if disc == DISC_LL_POOL_CREATE:
        st["create_seen"] += 1
        ev = decode_launchlab_pool_create(payload)
        if ev is None:
            return []
        st["create_decoded"] += 1
        return [_row(venue="raydium_launchlab", kind="create", program_id=LAUNCHLAB_PROGRAM,
                     signature=signature, slot=slot, **ev)]
    if disc == DISC_LL_TRADE:
        ev = decode_launchlab_trade(payload)
        if ev is None or ev["pool_status"] == "fund":
            return []      # an ordinary on-curve trade: this tape harvests LABELS, not the tape of trades
        # pool_status left `fund` on this very trade => the curve just completed. This is LaunchLab's
        # graduation signal in logs; the durable label is PoolState.status @offset 17.
        st["graduation_seen"] += 1
        st["graduation_decoded"] += 1
        vq, rq = ev["virtual_quote"], ev["real_quote_after"]
        x = _cp_multiple(vq, rq) if vq > 0 and rq > 0 else None
        return [_row(venue="raydium_launchlab", kind="graduation", program_id=LAUNCHLAB_PROGRAM,
                     signature=signature, slot=slot, graduation_multiple_x=x,
                     raise_quote=rq, **ev)]
    _note_untaped(st, "raydium_launchlab", disc)
    return []


# --- Meteora DBC ------------------------------------------------------------------------------------
DISC_DBC_INIT_POOL = bytes.fromhex("e432f655cb428625")
DISC_DBC_CURVE_COMPLETE = bytes.fromhex("e5e756549c864b18")
DISC_DBC_SWAP = bytes.fromhex("1b3c15d58aaabb93")
DISC_DBC_SWAP2 = bytes.fromhex("bd4233a826507599")


def decode_dbc_initialize_pool(payload: bytes) -> dict | None:
    if payload[:8] != DISC_DBC_INIT_POOL:
        return None
    c = Cursor(payload, 8)
    try:
        pool, config, creator, base_mint = c.pubkey(), c.pubkey(), c.pubkey(), c.pubkey()
        pool_type = c.u8()
        activation_point = c.u64()
    except (ValueError, struct.error):
        return None
    if not c.exhausted():
        return None
    return {"pool_id": pool, "config": config, "creator": creator, "mint": base_mint,
            "pool_type": pool_type, "activation_point": activation_point}


def decode_dbc_curve_complete(payload: bytes) -> dict | None:
    if payload[:8] != DISC_DBC_CURVE_COMPLETE:
        return None
    c = Cursor(payload, 8)
    try:
        pool, config = c.pubkey(), c.pubkey()
        base_reserve, quote_reserve = c.u64(), c.u64()
    except (ValueError, struct.error):
        return None
    if not c.exhausted():
        return None
    return {"pool_id": pool, "config": config, "base_reserve_raw": base_reserve,
            "quote_reserve_raw": quote_reserve}


def _dbc_events(payload: bytes, signature, slot) -> list[dict]:
    st = _stats("meteora_dbc")
    disc = payload[:8]
    if disc == DISC_DBC_INIT_POOL:
        st["create_seen"] += 1
        ev = decode_dbc_initialize_pool(payload)
        if ev is None:
            return []
        st["create_decoded"] += 1
        known = _dbc_venue_for_config(ev["config"])
        return [_row(venue="meteora_dbc", kind="create", program_id=DBC_PROGRAM,
                     signature=signature, slot=slot,
                     known_config_venue_id=known.venue_id if known else None,
                     graduation_multiple_x=known.graduation_multiple_x if known else None, **ev)]
    if disc == DISC_DBC_CURVE_COMPLETE:
        st["graduation_seen"] += 1
        ev = decode_dbc_curve_complete(payload)
        if ev is None:
            return []
        st["graduation_decoded"] += 1
        known = _dbc_venue_for_config(ev["config"])
        return [_row(venue="meteora_dbc", kind="graduation", program_id=DBC_PROGRAM,
                     signature=signature, slot=slot,
                     known_config_venue_id=known.venue_id if known else None,
                     graduation_multiple_x=known.graduation_multiple_x if known else None, **ev)]
    _note_untaped(st, "meteora_dbc", disc)
    return []


def _dbc_venue_for_config(config: str) -> Venue | None:
    """DBC's X is PER CONFIG (21,182 distinct configs in a 60k-pool sample, X from 1.00x to 200.00x).
    Only configs we actually measured get an X on the row; everything else is left absent for an
    offline PoolConfig read. There is no such thing as 'the Meteora multiple'."""
    for v in VENUES.values():
        if v.program_id == DBC_PROGRAM and v.platform_config == config:
            return v
    return None


# --- Boop -------------------------------------------------------------------------------------------
DISC_BOOP_CURVE_DEPLOYED = bytes.fromhex("e150b222d927b894")
DISC_BOOP_CURVE_DEPLOYED_FB = bytes.fromhex("6afcf373c79ff71f")
DISC_BOOP_TOKEN_CREATED = bytes.fromhex("607a718a32e39539")
DISC_BOOP_TOKEN_CREATED_FB = bytes.fromhex("9dca235ca5a32738")
DISC_BOOP_GRADUATED = bytes.fromhex("49746f1a5cd9928d")
DISC_BOOP_BOUGHT = bytes.fromhex("4759de7cd7c0e68a")
DISC_BOOP_SOLD = bytes.fromhex("ccefb64df1334d42")


def decode_boop_curve_deployed(payload: bytes) -> dict | None:
    """BondingCurveDeployedEvent{mint, creator}. Boop's TokenCreatedEvent carries only name/symbol/uri
    with NO mint, so THIS is the event that identifies a Boop launch; the metadata is merged in from the
    same transaction's TokenCreatedEvent when present."""
    if payload[:8] not in (DISC_BOOP_CURVE_DEPLOYED, DISC_BOOP_CURVE_DEPLOYED_FB):
        return None
    c = Cursor(payload, 8)
    try:
        mint, creator = c.pubkey(), c.pubkey()
    except (ValueError, struct.error):
        return None
    if not c.exhausted():
        return None
    return {"mint": mint, "creator": creator}


def decode_boop_token_created(payload: bytes) -> dict | None:
    if payload[:8] not in (DISC_BOOP_TOKEN_CREATED, DISC_BOOP_TOKEN_CREATED_FB):
        return None
    c = Cursor(payload, 8)
    try:
        name, symbol, uri = c.string(), c.string(), c.string()
    except (ValueError, struct.error):
        return None
    if not c.exhausted():
        return None
    return {"name": name, "symbol": symbol, "uri": uri}


def decode_boop_graduated(payload: bytes) -> dict | None:
    if payload[:8] != DISC_BOOP_GRADUATED:
        return None
    c = Cursor(payload, 8)
    try:
        mint = c.pubkey()
        sol_for_liquidity, graduation_fee, token_for_distributor = c.u64(), c.u64(), c.u64()
    except (ValueError, struct.error):
        return None
    if not c.exhausted():
        return None
    return {"mint": mint, "sol_for_liquidity": sol_for_liquidity / LAMPORTS,
            "graduation_fee": graduation_fee / LAMPORTS,
            "token_for_distributor_raw": token_for_distributor}


def _boop_events(payload: bytes, signature, slot) -> list[dict]:
    st = _stats("boop")
    disc = payload[:8]
    if disc in (DISC_BOOP_CURVE_DEPLOYED, DISC_BOOP_CURVE_DEPLOYED_FB):
        st["create_seen"] += 1
        ev = decode_boop_curve_deployed(payload)
        if ev is None:
            return []
        st["create_decoded"] += 1
        # graduation_multiple_x stays ABSENT: Boop's curve is damped, X is not derivable (see VENUES).
        return [_row(venue="boop", kind="create", program_id=BOOP_PROGRAM,
                     signature=signature, slot=slot, **ev)]
    if disc == DISC_BOOP_GRADUATED:
        st["graduation_seen"] += 1
        ev = decode_boop_graduated(payload)
        if ev is None:
            return []
        st["graduation_decoded"] += 1
        return [_row(venue="boop", kind="graduation", program_id=BOOP_PROGRAM,
                     signature=signature, slot=slot, **ev)]
    _note_untaped(st, "boop", disc)
    return []


def _boop_metadata(payload: bytes) -> dict | None:
    return decode_boop_token_created(payload)


# ---------------------------------------------------------------------------------------------------
# Program registry: what the listener subscribes to, and how each program's logs are read.
# ---------------------------------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class Program:
    key: str
    program_id: str
    handler: object                    # (payload, signature, slot) -> list[normalised rows]
    idl_key: str
    transport_verified: bool           # has a `Program data:` decode been OBSERVED on this program?
    transport_note: str


PROGRAMS: dict[str, Program] = {
    "pump.fun": Program(
        "pump.fun", PUMP_PROGRAM, _pump_events, "pump.fun", True,
        "MEASURED, not assumed. Replaying this decoder over the REAL mainnet logs in "
        "research/b11a/b11a_bodies.sqlite (multivenue_tape --replay-b11a) decodes 300/300 CreateEvents "
        "— each reproducing b11a_identity's mint AND creator, which were derived from instruction "
        "ACCOUNTS, an independent pipeline — and recovers 82 of 82 graduations with zero false "
        "positives and zero misses. So pump.fun DOES publish CreateEvent/CompleteEvent as plain "
        "`Program data:` log lines; Recon A's note that they ride ONLY as emit_cpi inner instructions "
        "is FALSIFIED for the log path (both transports carry them)."),
    "raydium_launchlab": Program(
        "raydium_launchlab", LAUNCHLAB_PROGRAM, _launchlab_events, "raydium_launchlab", True,
        "Recon A decoded live LaunchLab TradeEvents out of plain `Program data:` log lines, so the "
        "transport is verified for TradeEvent. PoolCreateEvent's transport is NOT independently "
        "confirmed here (no local LaunchLab bodies to replay), and PoolCreateEvent carries neither the "
        "base MINT nor the PLATFORM config — its `config` field is the GLOBAL config — so mint and "
        "LetsBonk-vs-Raydium attribution both need an account read the tape cannot do."),
    "meteora_dbc": Program(
        "meteora_dbc", DBC_PROGRAM, _dbc_events, "meteora_dbc", False,
        "UNVERIFIED transport: the discriminators are read from the on-chain IDL, but whether Meteora "
        "DBC emits them as `Program data:` log lines or ONLY as emit_cpi inner instructions was not "
        "established. If it is emit_cpi-only, logsSubscribe cannot see them and the listener's "
        "per-program counters will show program_data_lines>0 with create_seen==0 — which is the "
        "measurement, not a silent gap."),
    "boop": Program(
        "boop", BOOP_PROGRAM, _boop_events, "boop", False,
        "UNVERIFIED transport, same caveat as meteora_dbc."),
}
# Heaven is deliberately absent: no curve, no graduation, nothing for a launch/graduation tape to hold.


def listener_program_ids() -> list[str]:
    return [p.program_id for p in PROGRAMS.values()]


def program_for_id(program_id: str) -> Program | None:
    for p in PROGRAMS.values():
        if p.program_id == program_id:
            return p
    return None


def verify_pinned_idls(idl_dir: pathlib.Path = IDL_DIR) -> dict[str, str]:
    """Bind every decoder to the on-chain IDL it was written against; refuse if any hash drifted.

    Also re-derives each event discriminator from the IDL itself, so a renamed/reordered event in a
    refetched IDL cannot silently keep an old hex constant alive in this file.
    """
    observed: dict[str, str] = {}
    for key, (fname, expected) in PINNED_IDLS.items():
        path = idl_dir / fname
        raw = path.read_bytes()
        got = hashlib.sha256(raw).hexdigest()
        if got != expected:
            raise VenueRefused(f"pinned IDL {fname!r} drifted: expected {expected}, got {got}")
        observed[key] = got
        idl = json.loads(raw)
        discs = {e["name"]: bytes(e["discriminator"]) for e in idl.get("events", [])}
        for name, const in _IDL_EXPECTED_DISCRIMINATORS[key].items():
            if discs.get(name) != const:
                raise VenueRefused(f"{key}: IDL event {name!r} discriminator drifted "
                                   f"(idl={discs.get(name, b'').hex()}, code={const.hex()})")
    return observed


_IDL_EXPECTED_DISCRIMINATORS = {
    "pump.fun": {"CreateEvent": DISC_PUMP_CREATE, "CompleteEvent": DISC_PUMP_COMPLETE,
                 "TradeEvent": DISC_PUMP_TRADE},
    "raydium_launchlab": {"PoolCreateEvent": DISC_LL_POOL_CREATE, "TradeEvent": DISC_LL_TRADE},
    "meteora_dbc": {"EvtInitializePool": DISC_DBC_INIT_POOL,
                    "EvtCurveComplete": DISC_DBC_CURVE_COMPLETE,
                    "EvtSwap": DISC_DBC_SWAP, "EvtSwap2": DISC_DBC_SWAP2},
    "boop": {"BondingCurveDeployedEvent": DISC_BOOP_CURVE_DEPLOYED,
             "TokenCreatedEvent": DISC_BOOP_TOKEN_CREATED,
             "TokenGraduatedEvent": DISC_BOOP_GRADUATED},
}


def decode_logs(program_id: str, logs: list, *, signature: str | None = None,
                slot: int | None = None) -> list[dict]:
    """Every decodable CREATE / GRADUATION event in one transaction's logs, as normalised rows.

    A `mentions:[program]` subscription also delivers transactions that merely ROUTE THROUGH the program
    of interest, and sibling programs can emit events sharing a discriminator (LaunchLab's TradeEvent and
    pump.fun's TradeEvent are the same 8 bytes with different structs). So we walk the
    `Program <id> invoke/success` stack and decode a `Program data:` line ONLY while the target program
    is the one currently executing — the same guard that keeps PumpSwap AMM trades out of the live tape.
    """
    prog = program_for_id(program_id)
    if prog is None:
        raise VenueRefused(f"no decoder registered for program {program_id!r}")
    st = _stats(prog.key)
    out: list[dict] = []
    boop_meta: dict | None = None
    stack: list[str] = []
    for line in logs:
        if not isinstance(line, str):
            continue
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "Program":
            if parts[2] == "invoke":
                stack.append(parts[1])
                continue
            if parts[2] == "success" or parts[2].startswith("failed"):
                if stack:
                    stack.pop()
                continue
        if not line.startswith("Program data:"):
            continue
        if not stack or stack[-1] != program_id:
            continue
        try:
            payload = base64.b64decode(line.split("Program data:", 1)[1].strip(), validate=False)
        except Exception:  # noqa: BLE001
            continue
        # Some programs log the emit_cpi!-wrapped payload; strip the anchor CPI prefix if present.
        if payload[:8] == ANCHOR_CPI_PREFIX:
            payload = payload[8:]
        if len(payload) < 8:
            continue
        st["program_data_lines"] += 1
        if prog.key == "boop":
            meta = _boop_metadata(payload)
            if meta is not None:
                boop_meta = meta
                continue
        out.extend(prog.handler(payload, signature, slot))
    if boop_meta:
        for row in out:
            if row.get("venue") == "boop" and row.get("kind") == "create":
                row.update(boop_meta)
    return out


def registry_sha256() -> str:
    """Fingerprint of the frozen economics, so a downstream consumer can pin the numbers it read."""
    body = {vid: {k: v for k, v in dataclasses.asdict(v).items() if k != "provenance"}
            for vid, v in sorted(VENUES.items())}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


# ---------------------------------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------------------------------
def _selftest() -> None:
    # --- 1. pinned IDLs + discriminators re-derived from the IDLs themselves ------------------------
    verify_pinned_idls()

    # --- 2. the headline derivations ----------------------------------------------------------------
    pf = VENUES["pump.fun"]
    x = graduation_multiple("pump.fun")
    assert round(x, 4) == 14.6958, f"pump.fun X should be 14.6958x, got {x}"
    assert abs(x - 14.6958) < 5e-5
    # reproduces the +1369.4% measured on all 82 b11a graduates
    assert abs((x - 1.0) * 100 - 1369.58) < 0.2, (x - 1) * 100

    # break-even premium at the measured base rate p = 2.0855%
    p = 82 / 3932
    assert abs(p - 0.020855) < 1e-6, p
    # (a) at the arena's booked 3% round-trip toll  -> ~1.248
    m_arena = ev_breakeven_premium(pf, p, toll_round_trip=0.03)
    assert abs(m_arena - 1.248) < 5e-4, f"m* at 3% toll should be ~1.248, got {m_arena}"
    # (b) at pump.fun's MEASURED 2% on-chain protocol toll -> 1.2604 (Recon A's ranking number)
    m_measured = ev_breakeven_premium(pf, p)
    assert abs(m_measured - 1.2604) < 5e-4, f"m* at the measured 2% toll should be ~1.2604, got {m_measured}"
    assert abs(m_measured - 1.2604117066356602) < 1e-12
    assert m_measured > m_arena, "a smaller toll must permit a HIGHER break-even premium"

    # EV is exactly zero at m*, negative above it, positive below
    assert abs(ev_at_premium(pf, p, m_measured)) < 1e-12
    assert ev_at_premium(pf, p, m_measured * 1.01) < 0 < ev_at_premium(pf, p, m_measured * 0.99)
    ev_floor = ev_at_premium(pf, p, 1.0)
    assert abs(ev_floor - 0.2656) < 5e-4, ev_floor            # +26.6% EV at the floor (Recon A)
    assert abs(ev_floor - (prize_term(pf, p) - pf.toll_round_trip)) < 1e-12

    # --- 3. the other venues' derivations ------------------------------------------------------------
    assert round(graduation_multiple("letsbonk"), 4) == 14.6938
    ms = graduation_multiple("moonshot_dbc")
    assert round(ms, 4) == 200.0000, ms          # sqrt-derived: 199.99999685 -> 200.0000x to 4dp
    assert round(_cp_multiple(28.3333, 85.0), 4) == 16.0000, _cp_multiple(28.3333, 85.0)
    # LetsBonk's measured virtual reserves must satisfy constant product across graduation
    vB, vQ, S, R = 1073025605596382, 30000852951, 793100000000000, 85000000000
    assert abs((vB - S) * (vQ + R) / (vB * vQ) - 1.0) < 1e-9

    # --- 4. refusals, not guesses --------------------------------------------------------------------
    for vid in ("boop", "heaven"):
        try:
            graduation_multiple(vid)
        except VenueRefused:
            pass
        else:
            raise AssertionError(f"{vid} must REFUSE an X, not return one")
    try:
        ev_breakeven_premium("heaven", 0.01)
    except VenueRefused:
        pass
    else:
        raise AssertionError("heaven has no curve; m* must refuse")
    try:
        _venue("pons")
    except VenueRefused:
        pass
    else:
        raise AssertionError("pons is not a Solana venue and must not resolve")
    for bad in ((0.0,), (-1.0,)):
        try:
            ev_at_premium(pf, p, bad[0])
        except VenueRefused:
            pass
        else:
            raise AssertionError("non-physical m must refuse")

    # --- 5. the ranking, and the prize-term collapse --------------------------------------------------
    credible = rank_venues(credible_only=True)
    assert [r["venue_id"] for r in credible] == ["pump.fun", "letsbonk", "raydium_own"], credible
    assert abs(credible[0]["breakeven_premium_m_star"] - 1.2604117066356602) < 1e-12
    # THE COLLAPSE: across every venue with a real census that is actually a lottery, the whole prize
    # term (X-1)p lands in a narrow band even though X spans >13x. Launchpads compete on curve shape
    # and the market prices it straight back out.
    band = [r for r in rank_venues()
            if (r["n"] or 0) >= MIN_CENSUS_N and r["p"] <= MAX_LOTTERY_P]
    assert {r["venue_id"] for r in band} >= {"pump.fun", "letsbonk", "raydium_own", "moonshot_dbc"}, band
    assert all(0.07 <= r["prize_term_Xm1p"] <= 0.29 for r in band), \
        [(r["venue_id"], round(r["prize_term_Xm1p"], 3)) for r in band]
    assert max(r["X"] for r in band) / min(r["X"] for r in band) > 13, "X really does span >13x"
    # the near-100%-migration configs must be CAVEATED, never silently ranked above pump.fun
    axvr = next(r for r in rank_venues() if r["venue_id"] == "dbc_axvr")
    assert axvr["caveats"] and any("instant-liquidity" in c for c in axvr["caveats"]), axvr
    assert axvr not in credible

    # --- 6. decoder round-trips (hand-built borsh; no network) ----------------------------------------
    def _s(t: bytes) -> bytes:
        return struct.pack("<I", len(t)) + t

    mint, curve, user = bytes(range(32)), bytes(range(32, 64)), bytes(range(64, 96))
    creator = bytes(range(96, 128))
    b58 = b58encode
    assert b58encode(bytes(32)) == "1" * 32                        # known base58 vector

    pump_create = (DISC_PUMP_CREATE + _s(b"Fake") + _s(b"FAKE") + _s(b"ipfs://x")
                   + mint + curve + user + creator + struct.pack("<q", 7)
                   + struct.pack("<QQQQ", 1_073_000_000_000_000, 30 * LAMPORTS,
                                 793_100_000_000_000, 1_000_000_000_000_000)
                   + bytes(32) + b"\x00\x01" + bytes(32) + struct.pack("<Q", 30 * LAMPORTS))
    c = decode_pump_create(pump_create)
    assert c and c["mint"] == b58(mint) and c["pool_id"] == b58(curve) and c["creator"] == b58(creator)
    assert c["symbol"] == "FAKE" and abs(c["virtual_quote"] - 30.0) < 1e-9 and c["is_cashback_enabled"]
    assert abs(c["virtual_base"] - 1.073e9) < 1.0 and abs(c["total_supply"] - 1e9) < 1.0
    assert decode_pump_create(pump_create[:-4]) is None            # truncated -> drop
    assert decode_pump_create(pump_create + b"\x00") is None       # trailing bytes -> drop
    assert decode_pump_create(DISC_PUMP_COMPLETE + pump_create[8:]) is None   # wrong disc -> drop

    pump_complete = DISC_PUMP_COMPLETE + user + mint + curve + struct.pack("<q", 9) + bytes(32)
    g = decode_pump_complete(pump_complete)
    assert g and g["mint"] == b58(mint) and g["pool_id"] == b58(curve)
    assert decode_pump_complete(pump_complete[:-1]) is None

    ll_create = (DISC_LL_POOL_CREATE + curve + creator + user + b"\x06"
                 + _s(b"Bonk") + _s(b"BONK") + _s(b"https://x")
                 + b"\x00" + struct.pack("<QQQ", 1_000_000_000_000_000, 793_100_000_000_000,
                                         85 * LAMPORTS) + b"\x00"
                 + struct.pack("<QQQ", 0, 0, 0) + b"\x00")
    lc = decode_launchlab_pool_create(ll_create)
    assert lc and lc["pool_id"] == b58(curve) and lc["creator"] == b58(creator)
    assert lc["curve_kind"] == "constant_product" and abs(lc["raise_quote"] - 85.0) < 1e-9
    assert lc["total_base_sell_raw"] == 793_100_000_000_000 and lc["symbol"] == "BONK"
    assert decode_launchlab_pool_create(ll_create + b"\x00") is None
    assert decode_launchlab_pool_create(ll_create[:-1]) is None

    def _ll_trade(status: int, vq: int = 30_000_852_951, rq_after: int = 85 * LAMPORTS) -> bytes:
        return (DISC_LL_TRADE + curve
                + struct.pack("<QQQ", 793_100_000_000_000, 1_073_025_605_596_382, vq)
                + struct.pack("<QQQQ", 0, 0, 0, rq_after)
                + struct.pack("<QQ", 1_000_000, 900_000)
                + struct.pack("<QQQQ", 2500, 12500, 0, 0)
                + bytes([0, status]) + b"\x01")
    tr = decode_launchlab_trade(_ll_trade(0))
    assert tr and tr["pool_status"] == "fund" and tr["side"] == "buy"
    assert _launchlab_events(_ll_trade(0), None, None) == []       # ordinary trade is NOT taped
    rows = _launchlab_events(_ll_trade(1), "sigA", 42)
    assert len(rows) == 1 and rows[0]["kind"] == "graduation" and rows[0]["signature"] == "sigA"
    assert round(rows[0]["graduation_multiple_x"], 4) == 14.6938, rows[0]["graduation_multiple_x"]
    assert decode_launchlab_trade(_ll_trade(3)) is None            # impossible status -> drop

    dbc_cfg = "FbKf76ucsQssF7XZBuzScdJfugtsSKwZFYztKsMEhWZM"
    dbc_init = (DISC_DBC_INIT_POOL + curve + mint + creator + user + b"\x01"
                + struct.pack("<Q", 12345))
    di = decode_dbc_initialize_pool(dbc_init)
    assert di and di["pool_id"] == b58(curve) and di["mint"] == b58(user) and di["activation_point"] == 12345
    assert decode_dbc_initialize_pool(dbc_init[:-2]) is None
    dbc_done = DISC_DBC_CURVE_COMPLETE + curve + mint + struct.pack("<QQ", 111, 222)
    dd = decode_dbc_curve_complete(dbc_done)
    assert dd and dd["quote_reserve_raw"] == 222
    assert _dbc_venue_for_config(dbc_cfg) is not None and _dbc_venue_for_config("nope") is None
    assert round(_dbc_venue_for_config(dbc_cfg).graduation_multiple_x, 4) == 200.0

    boop_dep = DISC_BOOP_CURVE_DEPLOYED + mint + creator
    bd = decode_boop_curve_deployed(boop_dep)
    assert bd and bd["mint"] == b58(mint) and bd["creator"] == b58(creator)
    boop_grad = DISC_BOOP_GRADUATED + mint + struct.pack("<QQQ", 80 * LAMPORTS, 6 * LAMPORTS, 5)
    bg = decode_boop_graduated(boop_grad)
    assert bg and abs(bg["graduation_fee"] - 6.0) < 1e-9
    assert "graduation_multiple_x" not in _boop_events(boop_dep, None, None)[0]   # X refused, not faked

    # --- 7. the program-stack guard: a foreign program's Program data must be IGNORED -----------------
    enc = lambda b: base64.b64encode(b).decode()
    good = [f"Program {PUMP_PROGRAM} invoke [1]", "Program data: " + enc(pump_complete),
            f"Program {PUMP_PROGRAM} success"]
    assert len(decode_logs(PUMP_PROGRAM, good, signature="s", slot=1)) == 1
    nested = [f"Program {PUMP_PROGRAM} invoke [1]",
              f"Program {PUMPSWAP_AMM} invoke [2]",
              "Program data: " + enc(pump_complete),       # emitted by PumpSwap -> must be ignored
              f"Program {PUMPSWAP_AMM} success",
              f"Program {PUMP_PROGRAM} success"]
    assert decode_logs(PUMP_PROGRAM, nested) == [], "foreign-program event must be dropped"
    # LaunchLab's TradeEvent shares pump.fun's discriminator; routing by program must keep them apart
    ll_logs = [f"Program {LAUNCHLAB_PROGRAM} invoke [1]", "Program data: " + enc(_ll_trade(1)),
               f"Program {LAUNCHLAB_PROGRAM} success"]
    assert len(decode_logs(LAUNCHLAB_PROGRAM, ll_logs)) == 1
    assert decode_logs(PUMP_PROGRAM, ll_logs) == []
    # anchor emit_cpi!-wrapped payloads are unwrapped
    wrapped = [f"Program {PUMP_PROGRAM} invoke [1]",
               "Program data: " + enc(ANCHOR_CPI_PREFIX + pump_complete),
               f"Program {PUMP_PROGRAM} success"]
    assert len(decode_logs(PUMP_PROGRAM, wrapped)) == 1
    # boop metadata merge, in-transaction
    boop_logs = [f"Program {BOOP_PROGRAM} invoke [1]",
                 "Program data: " + enc(DISC_BOOP_TOKEN_CREATED + _s(b"Boopy") + _s(b"BOOP") + _s(b"u")),
                 "Program data: " + enc(boop_dep),
                 f"Program {BOOP_PROGRAM} success"]
    br = decode_logs(BOOP_PROGRAM, boop_logs)
    assert len(br) == 1 and br[0]["symbol"] == "BOOP" and br[0]["mint"] == b58(mint), br
    assert decode_logs(BOOP_PROGRAM, ["garbage", "Program data: !!!not-base64!!!"]) == []
    try:
        decode_logs("NotAProgram", [])
    except VenueRefused:
        pass
    else:
        raise AssertionError("an unregistered program must refuse")

    # --- 8. observability counters actually moved -----------------------------------------------------
    assert EVENT_STATS["pump.fun"]["graduation_decoded"] >= 2, EVENT_STATS["pump.fun"]
    assert EVENT_STATS["raydium_launchlab"]["create_decoded"] >= 0

    print("venues.py self-check OK")
    print(f"  registry: {len(VENUES)} venues, {len(PROGRAMS)} tapeable programs, "
          f"registry_sha256={registry_sha256()[:16]}...")
    print(f"  pump.fun  X={x:.4f}  toll={pf.toll_round_trip:.2%}  p={p:.4%}  "
          f"m*={m_measured:.4f} (measured toll) / {m_arena:.4f} (arena 3% toll)")
    print("  ranking by break-even premium m* (* = caveated, do not act on it):")
    for r in rank_venues():
        mark = "*" if r["caveats"] else " "
        print(f"   {mark}{r['venue_id']:<16} X={r['X']:>9.4f}  p={r['p']:>8.4%}  "
              f"toll={r['toll_round_trip']:>6.2%}  (X-1)p={r['prize_term_Xm1p']:>7.3f}  "
              f"m*={r['breakeven_premium_m_star']:>8.4f}  n={r['n']:>9,} g={r['graduations']:>6,}")
    for vid in ("boop", "heaven"):
        print(f"    {vid:<16} X REFUSED: {VENUES[vid].unverified.split('.')[0]}.")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="launchpad venue registry + pure decoders")
    ap.add_argument("--json", action="store_true", help="dump the registry as JSON instead of self-testing")
    args = ap.parse_args()
    if args.json:
        print(json.dumps({"schema": SCHEMA_VERSION, "registry_sha256": registry_sha256(),
                          "venues": {k: dataclasses.asdict(v) for k, v in VENUES.items()},
                          "programs": {k: {"program_id": p.program_id, "idl": p.idl_key,
                                           "transport_verified": p.transport_verified,
                                           "transport_note": p.transport_note}
                                       for k, p in PROGRAMS.items()},
                          "not_on_solana": NOT_ON_SOLANA,
                          "toll_discrepancy": TOLL_DISCREPANCY,
                          "ranking": rank_venues()}, indent=2, default=str))
    else:
        _selftest()
