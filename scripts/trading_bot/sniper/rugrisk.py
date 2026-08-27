#!/usr/bin/env python3
"""rugrisk.py — a deterministic ON-CHAIN RUG-RISK entry filter for the paper sniper stack.

PAPER / READ-ONLY. This module NEVER signs, sends, loads a wallet, or reads a private key. It only
READS the chain (JSON-RPC lookups) and the live tick stream, and scores how likely a memecoin is to
RUG. The point: the fattest losses in the live eval are the -1R catastrophes (rugs). If we can "read
the world better" and DECLINE the coins that will rug, we cut that tail. This is a FILTER on entry,
never a change to sizing or exits.

WHY THIS SHAPE
--------------
Given a mint at entry time we combine four tractable on-chain rug signals into one 0..1 score:

  (1) HOLDER CONCENTRATION  [LIVE, highest weight] — of the tokens actually in USER hands (the float,
      i.e. supply minus the bonding-curve reserve / AMM pool), how much do the top 1 / 5 / 10 wallets
      control? A float concentrated in a few wallets is a few wallets away from dumping on you.
      Also a "mega-rug" check: does any single wallet hold a large slice of TOTAL supply?

  (2) EARLY-BUYER / BUNDLE CONCENTRATION  [LIVE on the Chainstack feed] — in the first N seconds of a
      coin's life, how concentrated are the BUYS among distinct wallets? 3-5 wallets doing most of the
      early buying is the classic bundle/insider setup that dumps on late entrants.

  (3) LIQUIDITY TRAJECTORY  [LIVE, proxy] — is buy-pressure/liquidity GROWING or being pulled? Derived
      from net SOL flow in the recent window off the tick stream. A shrinking reserve (net outflow) is
      a rug precursor. At a fresh momentum-surge entry this is usually benign, so it carries low weight.

  (4) DEPLOYER REPUTATION  [COLD-START collector] — record each coin's deployer wallet (proxied by the
      dev's first observed buy) and, once a coin later resolves as a catastrophe in our own ledger,
      attribute a rug to that deployer. `is_known_rugger()` returns True once history exists. This needs
      DAYS of forward data to be useful, so its immediate weight is ~0; we build the DATA now.

RPC REALITY (measured 2026-08-26 on our Chainstack plan)
--------------------------------------------------------
  * `getTokenLargestAccounts` — BLOCKED (HTTP 403 / WAF). The "obvious" holder call is NOT available.
  * `getTokenSupply`, `getAccountInfo`, `getProgramAccounts` — ALLOWED.
  So holder concentration is done the robust way: `getProgramAccounts` on the SPL-Token-2022 program
  (pump.fun mints are Token-2022) filtered by a memcmp on the mint at offset 0, decode each token
  account's (owner, amount), aggregate by owner, and EXCLUDE the bonding-curve reserve. The reserve is
  identified two ways that agree: (a) the derived bonding-curve PDA `PDA(["bonding-curve", mint], PUMP)`
  — verified to match the reserve account's owner exactly on the live chain — and (b) any owner that is
  OFF the ed25519 curve (a program/PDA vault, never a user wallet).

FAIL-OPEN (documented decision)
-------------------------------
If we CANNOT assess a coin (RPC failed/timed out, or the holder call returned nothing), we ALLOW the
entry but FLAG it and count it against the coverage rate. Rationale: missing data must not halt trading,
and the honest metric is the coverage rate (what fraction of candidates we could actually assess). We
only BLOCK when we positively measured risk >= threshold — and, by default, only when the PRIMARY
holder-concentration signal was available (never block on proxy-only data).

DETERMINISTIC: no RNG, no LLM. Same inputs -> same score. Aggressively cached: one RPC holder lookup
per mint, memoized (success and failure), so a surge that fires across several variants costs one call.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import time
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

try:  # package context (run.py: `from .rugrisk import ...`)
    from .data._common import (
        RefusedError,
        b58encode,
        read_env,
        rpc_call,
    )
except ImportError:  # loose-script / selftest context: load the sibling helper by path
    import importlib.util as _ilu
    import pathlib as _pl

    _cmn_path = _pl.Path(__file__).resolve().parent / "data" / "_common.py"
    _spec = _ilu.spec_from_file_location("_rr_common", _cmn_path)
    _cmn = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_cmn)  # type: ignore[union-attr]
    RefusedError = _cmn.RefusedError
    b58encode = _cmn.b58encode
    read_env = _cmn.read_env
    rpc_call = _cmn.rpc_call


# --------------------------------------------------------------------------- program identities
PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"          # legacy SPL Token
TOKEN22_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"        # Token-2022 (pump.fun uses this)
# SPL token-account base layout (shared by legacy + Token-2022 base): mint[32] owner[32] amount(u64 LE)
_TA_MINT_OFF, _TA_OWNER_OFF, _TA_AMOUNT_OFF = 0, 32, 64
_TA_MIN_LEN = 72

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "research", "data", "sniper_cache")


# ======================================================================================================
# base58 decode + ed25519 on-curve test + program-derived-address (pure python, self-contained)
# ======================================================================================================
_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {c: i for i, c in enumerate(_B58_ALPHABET)}


def b58decode(s: str) -> bytes:
    """Decode a base58 (Solana/Bitcoin alphabet) string to raw bytes."""
    n = 0
    for ch in s:
        v = _B58_INDEX.get(ch)
        if v is None:
            raise ValueError(f"invalid base58 char {ch!r}")
        n = n * 58 + v
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + body


_ED_Q = 2 ** 255 - 19
_ED_D = (-121665 * pow(121666, _ED_Q - 2, _ED_Q)) % _ED_Q


def is_on_curve(pubkey_bytes: bytes) -> bool:
    """True iff a 32-byte ed25519 pubkey is a valid curve point. USER wallets are on-curve; PDAs /
    program vaults (bonding-curve reserve, AMM pools) are deliberately OFF-curve. So off-curve owner
    == "not a dumpable user holding". Robust to a rare false result: we also match the reserve by its
    exact derived PDA, and mis-classifying a user as a pool only makes the filter more lenient."""
    if len(pubkey_bytes) != 32:
        return False
    y = int.from_bytes(pubkey_bytes, "little")
    sign = (y >> 255) & 1
    y &= (1 << 255) - 1
    if y >= _ED_Q:
        return False
    u = (y * y - 1) % _ED_Q
    v = (_ED_D * y * y + 1) % _ED_Q
    if v == 0:
        return False
    x2 = (u * pow(v, _ED_Q - 2, _ED_Q)) % _ED_Q
    x = pow(x2, (_ED_Q + 3) // 8, _ED_Q)
    if (x * x - x2) % _ED_Q != 0:
        x = (x * pow(2, (_ED_Q - 1) // 4, _ED_Q)) % _ED_Q
    if (x * x - x2) % _ED_Q != 0:
        return False
    if x == 0 and sign:
        return False
    return True


def find_program_address(seeds: list[bytes], program_id: str) -> Optional[str]:
    """Solana findProgramAddress: the first OFF-curve address for these seeds + program, or None."""
    prog = b58decode(program_id)
    for bump in range(255, -1, -1):
        h = hashlib.sha256()
        for s in seeds:
            h.update(s)
        h.update(bytes([bump]))
        h.update(prog)
        h.update(b"ProgramDerivedAddress")
        cand = h.digest()
        if not is_on_curve(cand):
            return b58encode(cand)
    return None


def bonding_curve_pda(mint: str) -> Optional[str]:
    """The pump.fun bonding-curve PDA for a mint = PDA(["bonding-curve", mint], PUMP_PROGRAM). Its ATA
    holds the reserve; the reserve token-account's OWNER is this PDA (verified on live chain)."""
    try:
        return find_program_address([b"bonding-curve", b58decode(mint)], PUMP_PROGRAM)
    except ValueError:
        return None


# ======================================================================================================
# configuration
# ======================================================================================================
@dataclass(frozen=True)
class RugConfig:
    """All knobs + PRE-REGISTERED weights/thresholds. NOT tuned to any observed outcome — set once, up
    front, and adjudicated only by the forward comparison (filtered vs unfiltered ledger)."""
    # --- combination weights (sum ~1.0; score is a weighted mean over AVAILABLE components) ---
    w_holder: float = 0.60      # holder concentration — the high-value signal
    w_early: float = 0.25       # early-buyer / bundle concentration
    w_liquidity: float = 0.10   # liquidity trajectory (proxy; usually benign at a surge)
    w_deployer: float = 0.05    # deployer reputation (cold-start; ~0 until history exists)

    block_threshold: float = 0.55       # block entry when score >= this
    require_primary_for_block: bool = True  # only block if holder concentration was actually assessed

    # --- holder concentration mapping (fractions of the FLOAT = non-reserve circulating supply) ---
    min_float_frac: float = 0.01        # need >=1% of supply in user hands before concentration means anything
    top1_ramp: tuple = (0.30, 0.60)     # top-1 wallet share of float: 30%->60% maps risk 0->1
    top5_ramp: tuple = (0.60, 0.90)     # top-5 share of float
    top10_ramp: tuple = (0.80, 0.98)    # top-10 share of float
    mega_supply_ramp: tuple = (0.15, 0.35)  # top-1 share of TOTAL supply (dev kept a huge bag)

    # --- early-buyer / bundle mapping ---
    early_window_s: float = 30.0        # "early" = first N seconds after a mint is first seen
    early_min_buyers: int = 4           # need at least this many distinct early buyers to judge share...
    early_min_buy_usd: float = 100.0    # ...and this much early buy USD (else: not enough to assess)
    early_top3_ramp: tuple = (0.60, 0.90)   # top-3 wallets' share of early buy USD: 60%->90% maps 0->1
    early_fewbuyers_at: int = 3         # <= this many distinct early buyers doing all the buying = bundle

    # --- liquidity trajectory mapping ---
    liq_window_s: float = 60.0          # recent window for net-flow trajectory
    liq_min_usd: float = 200.0          # need this much flow before judging trajectory
    liq_sellfrac_ramp: tuple = (0.55, 0.80)  # sell USD fraction over the window: 55%->80% maps 0->1

    # --- RPC caching ---
    rpc_timeout_s: float = 8.0
    ok_ttl_s: float = 180.0             # cache a successful holder read this long
    fail_ttl_s: float = 30.0            # cache a failure briefly (don't hammer a struggling RPC)
    max_holder_accounts: int = 6000     # safety cap: skip absurdly large enumerations (fail-open)


def _ramp(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 1.0 if x >= hi else 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


# ======================================================================================================
# holder-concentration result
# ======================================================================================================
@dataclass(frozen=True)
class HolderConcentration:
    mint: str
    supply: int
    n_holders: int              # distinct USER (on-curve, non-reserve) owners
    reserve_amount: int         # tokens held by the bonding-curve reserve / pools (excluded)
    circulating: int            # supply in user hands = supply - reserve
    float_frac: float           # circulating / supply
    top1_frac: float            # top-1 user share of the FLOAT
    top5_frac: float
    top10_frac: float
    top1_supply_frac: float     # top-1 user share of TOTAL supply (mega-rug frame)
    component: float            # 0..1 holder-concentration risk
    token_program: str


# ======================================================================================================
# early-buyer / bundle tracker (fed from the live tick stream)
# ======================================================================================================
class EarlyBuyerTracker:
    """Per-mint accumulation of BUY USD by wallet within the first `early_window_s` seconds of the first
    time we saw the mint. Read-only bookkeeping over the tick stream — no RPC, no wallet."""

    def __init__(self, cfg: RugConfig) -> None:
        self.cfg = cfg
        self._first_seen: dict[str, float] = {}
        self._buys: dict[str, dict[str, float]] = {}   # mint -> {wallet -> buy usd within window}
        self._n_early_trades: dict[str, int] = {}

    def observe(self, mint: str, ts: float, side: str, user: Optional[str], usd: float) -> None:
        first = self._first_seen.get(mint)
        if first is None:
            first = self._first_seen[mint] = ts
        if ts - first > self.cfg.early_window_s:
            return  # past the early window; frozen
        if side != "buy" or not user or usd <= 0:
            return
        wallets = self._buys.setdefault(mint, {})
        wallets[user] = wallets.get(user, 0.0) + float(usd)
        self._n_early_trades[mint] = self._n_early_trades.get(mint, 0) + 1

    def assess(self, mint: str) -> tuple[Optional[float], dict]:
        """Return (component 0..1 or None if unassessable, detail). Concentrated early buying by few
        wallets -> high component."""
        wallets = self._buys.get(mint) or {}
        total = sum(wallets.values())
        n = len(wallets)
        detail = {"n_early_buyers": n, "early_buy_usd": round(total, 2),
                  "n_early_trades": self._n_early_trades.get(mint, 0)}
        if n == 0 or total < self.cfg.early_min_buy_usd:
            detail["assessed"] = False
            return None, detail
        top = sorted(wallets.values(), reverse=True)
        top3_share = sum(top[:3]) / total if total > 0 else 0.0
        detail.update(top1_share=round(top[0] / total, 4), top3_share=round(top3_share, 4))
        # Bundle heuristics: a large top-3 share OR nearly-all buying by <= few distinct wallets.
        comp = _ramp(top3_share, *self.cfg.early_top3_ramp)
        if n <= self.cfg.early_fewbuyers_at and top3_share >= 0.85:
            comp = max(comp, 0.85)
        # Not enough distinct buyers to trust the share yet (but keep a floor if it already looks bundled).
        if n < self.cfg.early_min_buyers:
            detail["assessed"] = comp >= 0.85
            return (comp if comp >= 0.85 else None), detail
        detail["assessed"] = True
        return comp, detail

    def prune(self, now_ts: float, idle_s: float = 900.0) -> None:
        for mint, first in list(self._first_seen.items()):
            if now_ts - first > idle_s:
                self._first_seen.pop(mint, None)
                self._buys.pop(mint, None)
                self._n_early_trades.pop(mint, None)


# ======================================================================================================
# liquidity-trajectory tracker (fed from the live tick stream)
# ======================================================================================================
class LiquidityTracker:
    """Rolling per-mint buy/sell USD over `liq_window_s`. A window dominated by SELL flow == liquidity
    being pulled == rug precursor. Cheap running sums off the tick stream; no RPC."""

    def __init__(self, cfg: RugConfig) -> None:
        self.cfg = cfg
        from collections import deque, defaultdict
        self._ev: dict[str, deque] = defaultdict(deque)   # mint -> deque[(ts, buy_usd, sell_usd)]
        self._buy: dict[str, float] = defaultdict(float)
        self._sell: dict[str, float] = defaultdict(float)

    def observe(self, mint: str, ts: float, side: str, usd: float) -> None:
        dq = self._ev[mint]
        b = float(usd) if side == "buy" else 0.0
        s = float(usd) if side == "sell" else 0.0
        dq.append((ts, b, s))
        self._buy[mint] += b
        self._sell[mint] += s
        horizon = ts - self.cfg.liq_window_s
        while dq and dq[0][0] < horizon:
            _, ob, os_ = dq.popleft()
            self._buy[mint] -= ob
            self._sell[mint] -= os_
        if not dq:
            self._buy[mint] = 0.0
            self._sell[mint] = 0.0

    def assess(self, mint: str) -> tuple[Optional[float], dict]:
        buy = self._buy.get(mint, 0.0)
        sell = self._sell.get(mint, 0.0)
        flow = buy + sell
        detail = {"win_buy_usd": round(buy, 2), "win_sell_usd": round(sell, 2)}
        if flow < self.cfg.liq_min_usd:
            detail["assessed"] = False
            return None, detail
        sellfrac = sell / flow
        detail.update(sell_frac=round(sellfrac, 4), assessed=True)
        return _ramp(sellfrac, *self.cfg.liq_sellfrac_ramp), detail

    def prune(self, now_ts: float, idle_s: float = 900.0) -> None:
        for mint, dq in list(self._ev.items()):
            if not dq or now_ts - dq[-1][0] > idle_s:
                self._ev.pop(mint, None)
                self._buy.pop(mint, None)
                self._sell.pop(mint, None)


# ======================================================================================================
# deployer-reputation registry (cold-start collector; persistent JSON)
# ======================================================================================================
class DeployerRegistry:
    """Records mint -> deployer (proxied by the dev's FIRST observed buy) and deployer -> rug history.
    Outcomes are ingested from our OWN resolved ledger: a mint that exits `catastrophe` counts as a rug
    for its deployer. Cold-start: returns a real signal only after days of forward data accumulate.

    NOTE ON THE PROXY: the true deployer is the create-instruction signer. Parsing that needs a
    getTransaction on the create tx (an extra RPC + instruction decode). As a tractable stand-in we use
    the earliest observed BUYER of the mint, which on pump.fun is almost always the dev's launch buy.
    Documented as a proxy; can be upgraded to the true creator later without changing the interface."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or os.path.join(CACHE_DIR, "rug_deployers.json")
        self._mint_deployer: dict[str, str] = {}
        self._deployer_stats: dict[str, dict] = {}   # wallet -> {"coins": n, "rugs": n, "mints": [...]}
        self._ingested: set[str] = set()             # mints whose outcome we've already counted
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path) as fh:
                d = json.load(fh)
            self._mint_deployer = d.get("mint_deployer", {})
            self._deployer_stats = d.get("deployer_stats", {})
            self._ingested = set(d.get("ingested", []))
        except (OSError, ValueError):
            pass

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump({"mint_deployer": self._mint_deployer,
                           "deployer_stats": self._deployer_stats,
                           "ingested": sorted(self._ingested)}, fh)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def record_deployer(self, mint: str, wallet: Optional[str]) -> None:
        if not wallet or mint in self._mint_deployer:
            return
        self._mint_deployer[mint] = wallet
        stats = self._deployer_stats.setdefault(wallet, {"coins": 0, "rugs": 0, "mints": []})
        if mint not in stats["mints"]:
            stats["coins"] += 1
            stats["mints"].append(mint)
        self._save()

    def record_outcome(self, mint: str, rugged: bool) -> bool:
        """Attribute a resolved outcome to the mint's deployer. Idempotent per mint. Returns True if it
        recorded a NEW rug (useful for callers/tests)."""
        if mint in self._ingested:
            return False
        wallet = self._mint_deployer.get(mint)
        self._ingested.add(mint)
        new_rug = False
        if wallet and rugged:
            stats = self._deployer_stats.setdefault(wallet, {"coins": 0, "rugs": 0, "mints": []})
            stats["rugs"] += 1
            new_rug = True
        self._save()
        return new_rug

    def ingest_ledger(self, ledger_path: str, rug_reasons=("exit:catastrophe",)) -> dict:
        """Scan a resolved per-variant ledger (jsonl) and record each mint's outcome once. A trade whose
        exit_reason is a rug-reason (a -1R catastrophe) marks its deployer. Returns a small summary."""
        seen = 0
        rugs = 0
        try:
            with open(ledger_path) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    mint = row.get("mint")
                    if not mint or mint in self._ingested:
                        continue
                    rugged = row.get("exit_reason") in rug_reasons
                    if self.record_outcome(mint, rugged):
                        rugs += 1
                    seen += 1
        except OSError:
            pass
        return {"newly_ingested": seen, "new_rugs": rugs}

    def is_known_rugger(self, wallet: Optional[str]) -> dict:
        stats = self._deployer_stats.get(wallet or "", {})
        rugs = stats.get("rugs", 0)
        coins = stats.get("coins", 0)
        return {"known": rugs > 0, "rugs": rugs, "coins": coins,
                "rug_rate": (rugs / coins) if coins else 0.0}

    def assess(self, mint: str) -> tuple[float, dict]:
        wallet = self._mint_deployer.get(mint)
        info = self.is_known_rugger(wallet)
        detail = {"deployer": wallet, **info}
        # Component: 1.0 if this deployer has a prior rug, scaled a touch by their rug-rate. 0 otherwise.
        comp = 0.0
        if info["known"]:
            comp = min(1.0, 0.6 + 0.4 * info["rug_rate"])
        return comp, detail


# ======================================================================================================
# the combined assessment
# ======================================================================================================
@dataclass
class RugAssessment:
    mint: str
    score: float                       # 0..1 combined rug-risk (weighted mean over available components)
    blocked: bool                      # would this block entry at the configured threshold?
    assessed: bool                     # did we get ANY component? (False => fully unassessed, fail-open)
    holder_assessed: bool              # did the PRIMARY (holder concentration) signal succeed?
    components: dict = field(default_factory=dict)   # name -> value (only those available)
    detail: dict = field(default_factory=dict)       # per-signal diagnostics
    reason: str = ""


# ======================================================================================================
# the scorer
# ======================================================================================================
class RugRiskScorer:
    """Deterministic rug-risk scorer. Feed it every tick via `observe_tick` (cheap, no RPC); ask it for
    `rug_score(mint)` at entry time (one cached RPC holder lookup per mint)."""

    def __init__(self, cfg: Optional[RugConfig] = None, rpc_url: Optional[str] = None,
                 deployer_path: Optional[str] = None) -> None:
        self.cfg = cfg or RugConfig()
        self._rpc_url = rpc_url if rpc_url is not None else read_env("SOLANA_RPC_URL")
        self.early = EarlyBuyerTracker(self.cfg)
        self.liquidity = LiquidityTracker(self.cfg)
        self.deployers = DeployerRegistry(deployer_path)
        # holder-concentration cache: mint -> (expiry_ts, HolderConcentration|None)
        self._hc_cache: dict[str, tuple] = {}
        # coverage counters (honesty metric)
        self.n_candidates = 0
        self.n_holder_ok = 0
        self.n_rpc_calls = 0

    # -------------------- stream ingestion (no RPC) --------------------
    def observe_tick(self, tick) -> None:
        """Feed one live TradeTick. Populates early-buyer, liquidity, and deployer first-seen state.
        `tick.user` (the trader wallet) is used when present (Chainstack feed carries it)."""
        user = getattr(tick, "user", None)
        self.early.observe(tick.mint, tick.ts, tick.side, user, tick.usd)
        self.liquidity.observe(tick.mint, tick.ts, tick.side, tick.usd)
        if tick.side == "buy" and user:
            self.deployers.record_deployer(tick.mint, user)

    def prune(self, now_ts: float) -> None:
        self.early.prune(now_ts)
        self.liquidity.prune(now_ts)

    # -------------------- holder concentration (RPC, cached) --------------------
    def holder_concentration(self, mint: str) -> Optional[HolderConcentration]:
        """One cached RPC holder read per mint. Returns None if unassessable (RPC blocked/failed/empty).
        Success and failure are both cached (different TTLs) so a coin is looked up at most once."""
        now = time.time()
        cached = self._hc_cache.get(mint)
        if cached is not None and cached[0] > now:
            return cached[1]
        result = self._fetch_holder_concentration(mint)
        ttl = self.cfg.ok_ttl_s if result is not None else self.cfg.fail_ttl_s
        self._hc_cache[mint] = (now + ttl, result)
        return result

    def _enumerate_token_accounts(self, mint: str) -> tuple[Optional[list], Optional[str]]:
        """Return (list[(amount:int, owner:str)], token_program) for a mint, or (None, None). Tries
        Token-2022 first (pump.fun), then legacy SPL Token with the fixed 165-byte size filter."""
        if not self._rpc_url:
            return None, None
        attempts = [
            (TOKEN22_PROGRAM, [{"memcmp": {"offset": _TA_MINT_OFF, "bytes": mint}}]),
            (TOKEN_PROGRAM, [{"dataSize": 165}, {"memcmp": {"offset": _TA_MINT_OFF, "bytes": mint}}]),
        ]
        for program, filters in attempts:
            params = [program, {"encoding": "base64", "filters": filters}]
            try:
                self.n_rpc_calls += 1
                raw = rpc_call(self._rpc_url, "getProgramAccounts", params, timeout=self.cfg.rpc_timeout_s)
            except (RefusedError, urllib.error.URLError, OSError, ValueError, TimeoutError):
                continue
            if not raw:
                continue
            if len(raw) > self.cfg.max_holder_accounts:
                # Too many holders to enumerate cheaply -> treat as unassessable (fail-open), not an error.
                return None, None
            accounts = []
            for item in raw:
                try:
                    data = base64.b64decode(item["account"]["data"][0])
                except (KeyError, IndexError, ValueError, TypeError):
                    continue
                if len(data) < _TA_MIN_LEN:
                    continue
                owner = b58encode(data[_TA_OWNER_OFF:_TA_OWNER_OFF + 32])
                amount = struct.unpack_from("<Q", data, _TA_AMOUNT_OFF)[0]
                accounts.append((amount, owner))
            if accounts:
                return accounts, program
        return None, None

    def _fetch_holder_concentration(self, mint: str) -> Optional[HolderConcentration]:
        accounts, program = self._enumerate_token_accounts(mint)
        if not accounts:
            return None
        # authoritative supply
        supply = 0
        try:
            self.n_rpc_calls += 1
            sup = rpc_call(self._rpc_url, "getTokenSupply", [mint], timeout=self.cfg.rpc_timeout_s)
            supply = int(((sup or {}).get("value") or {}).get("amount") or 0)
        except (RefusedError, urllib.error.URLError, OSError, ValueError, TimeoutError):
            supply = 0
        if supply <= 0:
            supply = sum(a for a, _ in accounts)  # fall back to the enumerated total
        if supply <= 0:
            return None

        reserve_pda = bonding_curve_pda(mint)
        # aggregate by owner; split reserve/pool (off-curve owner OR the derived bonding-curve PDA)
        by_owner: dict[str, int] = {}
        for amount, owner in accounts:
            by_owner[owner] = by_owner.get(owner, 0) + amount
        reserve = 0
        users: list[int] = []
        for owner, amount in by_owner.items():
            if owner == reserve_pda or not is_on_curve(b58decode(owner)):
                reserve += amount
            else:
                users.append(amount)
        users.sort(reverse=True)
        circulating = sum(users)
        float_frac = circulating / supply if supply else 0.0

        def share(k: int) -> float:
            return (sum(users[:k]) / circulating) if circulating > 0 else 0.0

        top1, top5, top10 = share(1), share(5), share(10)
        top1_supply = (users[0] / supply) if users else 0.0

        # component: max of the framed risks, but only when there's enough FLOAT to judge.
        if float_frac < self.cfg.min_float_frac:
            component = 0.0   # almost nothing bought yet — high top-k is just "brand new", not a rug
        else:
            component = max(
                _ramp(top1, *self.cfg.top1_ramp),
                _ramp(top5, *self.cfg.top5_ramp),
                _ramp(top10, *self.cfg.top10_ramp),
            )
        # mega-rug (dev kept a huge share of TOTAL supply) always counts, independent of float
        component = max(component, _ramp(top1_supply, *self.cfg.mega_supply_ramp))

        return HolderConcentration(
            mint=mint, supply=supply, n_holders=len(users), reserve_amount=reserve,
            circulating=circulating, float_frac=float_frac, top1_frac=top1, top5_frac=top5,
            top10_frac=top10, top1_supply_frac=top1_supply, component=round(component, 4),
            token_program=program or "",
        )

    # -------------------- combined score --------------------
    def rug_score(self, mint: str, ctx: Optional[dict] = None) -> RugAssessment:
        """Combine the four signals into a 0..1 rug-risk score for `mint` at entry time. Deterministic.
        Fail-OPEN: an unassessable signal is simply omitted from the weighted mean; a fully-unassessable
        coin scores 0 and is allowed (but flagged, and counted against coverage)."""
        self.n_candidates += 1
        cfg = self.cfg
        components: dict = {}
        detail: dict = {}
        weights: dict = {}

        # (1) holder concentration — the primary signal
        hc = self.holder_concentration(mint)
        holder_assessed = hc is not None
        if hc is not None:
            self.n_holder_ok += 1
            components["holder"] = hc.component
            weights["holder"] = cfg.w_holder
            detail["holder"] = {
                "n_user_holders": hc.n_holders, "float_frac": round(hc.float_frac, 5),
                "top1_frac_float": round(hc.top1_frac, 4), "top5_frac_float": round(hc.top5_frac, 4),
                "top10_frac_float": round(hc.top10_frac, 4),
                "top1_frac_supply": round(hc.top1_supply_frac, 4),
                "reserve_frac": round(1.0 - hc.float_frac, 5), "token_program": hc.token_program,
            }
        else:
            detail["holder"] = {"assessed": False}

        # (2) early-buyer / bundle concentration
        eb_comp, eb_detail = self.early.assess(mint)
        detail["early"] = eb_detail
        if eb_comp is not None:
            components["early"] = eb_comp
            weights["early"] = cfg.w_early

        # (3) liquidity trajectory
        lt_comp, lt_detail = self.liquidity.assess(mint)
        detail["liquidity"] = lt_detail
        if lt_comp is not None:
            components["liquidity"] = lt_comp
            weights["liquidity"] = cfg.w_liquidity

        # (4) deployer reputation (always available; 0 unless a known rugger)
        dep_comp, dep_detail = self.deployers.assess(mint)
        detail["deployer"] = dep_detail
        components["deployer"] = dep_comp
        weights["deployer"] = cfg.w_deployer

        # weighted mean over AVAILABLE components
        wsum = sum(weights.values())
        score = (sum(components[k] * weights[k] for k in weights) / wsum) if wsum > 0 else 0.0
        score = round(score, 4)

        assessed = holder_assessed or eb_comp is not None or lt_comp is not None or dep_comp > 0
        blocked = self.blocks_entry(score, holder_assessed=holder_assessed)
        reason = self._reason(score, blocked, holder_assessed, components)
        return RugAssessment(mint=mint, score=score, blocked=blocked, assessed=assessed,
                             holder_assessed=holder_assessed, components=components,
                             detail=detail, reason=reason)

    def blocks_entry(self, score, threshold: Optional[float] = None, holder_assessed: bool = True) -> bool:
        """The entry gate. Blocks iff score >= threshold — and, when require_primary_for_block is set,
        only if the holder-concentration signal was actually available (never block on proxy-only data).
        Accepts a float score or a RugAssessment."""
        if isinstance(score, RugAssessment):
            holder_assessed = score.holder_assessed
            score = score.score
        thr = self.cfg.block_threshold if threshold is None else threshold
        if self.cfg.require_primary_for_block and not holder_assessed:
            return False
        return score >= thr

    def _reason(self, score, blocked, holder_assessed, components) -> str:
        top = max(components.items(), key=lambda kv: kv[1]) if components else ("none", 0.0)
        state = "BLOCK" if blocked else ("ALLOW" if holder_assessed else "ALLOW(unassessed)")
        return f"{state} score={score:.3f} top={top[0]}:{top[1]:.2f}"

    def coverage(self) -> dict:
        rate = (self.n_holder_ok / self.n_candidates) if self.n_candidates else 0.0
        return {"candidates": self.n_candidates, "holder_assessed": self.n_holder_ok,
                "coverage_rate": round(rate, 4), "rpc_calls": self.n_rpc_calls}


# ======================================================================================================
# tiny live demo (READ-ONLY) — `python -m scripts.trading_bot.sniper.rugrisk <mint> [<mint> ...]`
# ======================================================================================================
def _demo(mints: list[str]) -> int:
    scorer = RugRiskScorer()
    if not scorer._rpc_url:
        print("SOLANA_RPC_URL not set; cannot run live demo.")
        return 1
    for mint in mints:
        hc = scorer.holder_concentration(mint)
        if hc is None:
            print(f"\n{mint}\n  holder concentration: UNASSESSABLE (RPC blocked/empty) -> fail-open ALLOW")
            continue
        print(f"\n{mint}  [{hc.token_program[:6]}..]")
        print(f"  supply={hc.supply}  user_holders={hc.n_holders}  "
              f"float={hc.float_frac*100:.2f}% (reserve {100*(1-hc.float_frac):.2f}%)")
        print(f"  top1/top5/top10 of FLOAT = {hc.top1_frac*100:.1f}% / {hc.top5_frac*100:.1f}% / "
              f"{hc.top10_frac*100:.1f}%   top1 of SUPPLY = {hc.top1_supply_frac*100:.2f}%")
        assess = scorer.rug_score(mint)
        print(f"  -> {assess.reason}  (blocked={assess.blocked})")
    print("\ncoverage:", scorer.coverage())
    return 0


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if not args:
        args = ["2BSZ36W4QAiEtZjPYvRF9S7UKm4EJr76Y7hdBuhepump",
                "4MzpjwjkWn7628mEMqasz5RyFU3tDhyoXXCegmvUpump"]
    raise SystemExit(_demo(args))
