#!/usr/bin/env python3
"""Launch-Window Sentinel Scalper — the deadness / insider-footprint entry screen (PAPER-SCENARIO).

Pure, no I/O, no lookahead. This is the LIVE replica of the ONE leakage-audited finding in the whole
programme — B20B (research/B20B_DEADNESS_SCREEN.md): at t0+60 slots, if the single largest buyer holds
>= 0.95 of all tokens bought so far, the token is unexitable (nobody else showed up = no external money
to exit into) -> refuse entry. It is DEFENSE, not an edge: B20B's own text states screening out dead
tokens does not make survivors profitable.

The feature is computed from the decoded TradeEvent `token_amount` (atoms), BYTE-IDENTICALLY to
scripts/b20b_deadness_screen_runner.py `score` (held[user] += token_amount if buy else -token_amount;
total = sum positive; flagged = top*100 >= total*95). We import b20b's frozen constants read-only and
assert them at import so the 60/95/2 rule cannot drift (b20b is pinned in the seal closure).

Additional insider-footprint signals (dev-share, same-slot bundle) are computed and returned but are
SHADOW-ONLY / NON-DECISIONAL — logged for later attribution, never gating, until their own forward
attribution column earns promotion. Promoting them now would be fitting beyond B20B's audited scope.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .execution import RefusedExecution

# Frozen rule, pinned to the validated source. Import is side-effect-free (b20b's main is __main__-guarded).
try:  # pragma: no cover - import wiring
    import importlib
    _b20b = importlib.import_module("scripts.b20b_deadness_screen_runner")
    K_SLOTS = int(_b20b.K_SLOTS)
    CONCENTRATION_THRESHOLD = int(_b20b.CONCENTRATION_THRESHOLD)
    MIN_BUYERS_TO_SCORE = int(_b20b.MIN_BUYERS_TO_SCORE)
except Exception:  # the runner may not be importable in every context; fall back to the frozen literals
    K_SLOTS, CONCENTRATION_THRESHOLD, MIN_BUYERS_TO_SCORE = 60, 95, 2

# The frozen rule this screen commits to. If b20b ever drifts from these, the seal (which pins b20b)
# changes and this instrument must be re-sealed — never silently follow a moved rule.
FROZEN_K_SLOTS = 60
FROZEN_CONCENTRATION_THRESHOLD = 95
FROZEN_MIN_BUYERS = 2
if (K_SLOTS, CONCENTRATION_THRESHOLD, MIN_BUYERS_TO_SCORE) != (
        FROZEN_K_SLOTS, FROZEN_CONCENTRATION_THRESHOLD, FROZEN_MIN_BUYERS):
    raise RefusedExecution("PAC_LWS screen: b20b frozen rule drifted from the pinned 60/95/2")

# verdict statuses
SURVIVED = "SCREEN_SURVIVED"
VETO_CONCENTRATION = "VETO_CONCENTRATION"   # the sealed B20B veto
UNREADABLE = "UNREADABLE"                    # < 2 buyers -> refuse entry (NOT a screened verdict)
NO_NET = "NO_NET_TOKENS"                     # no positive net buying -> refuse entry


@dataclass(frozen=True)
class WindowTrade:
    """One in-window trade, already decoded. token_amount is atoms (from decode_pump_trades_from_logs).
    reserve_delta_tokens is (pre.real_token - post.real_token) if available, else None (cross-check)."""
    slot: int
    trader: str
    is_buy: bool
    token_amount: int
    reserve_delta_tokens: int | None = None

    def __post_init__(self) -> None:
        if type(self.slot) is not int or type(self.token_amount) is not int:
            raise RefusedExecution("PAC_LWS window trade slot/amount must be exact integers")
        if self.token_amount < 0 or not isinstance(self.trader, str) or not self.trader:
            raise RefusedExecution("PAC_LWS window trade is malformed")


@dataclass(frozen=True)
class ScreenVerdict:
    status: str
    flagged: bool
    top_share_bps: int
    buyers: int
    net_total_atoms: int
    validated_trades: int
    dropped_crosscheck: int
    shadow: dict = field(default_factory=dict)

    @property
    def enter_allowed(self) -> bool:
        # only a screen-survived verdict admits an entry; unreadable / no-net / veto all refuse.
        return self.status == SURVIVED


def _window(trades, t0_slot: int):
    if type(t0_slot) is not int:
        raise RefusedExecution("PAC_LWS screen requires an exact integer t0_slot")
    return [t for t in trades if t0_slot <= t.slot <= t0_slot + K_SLOTS]


def evaluate(trades, *, t0_slot: int, dev_wallet: str | None = None,
             crosscheck_rounding_atoms: int = 0) -> ScreenVerdict:
    """Return the sealed B20B verdict over [t0, t0+60] plus shadow footprint signals.

    ``trades`` are WindowTrade for this mint (any slots; only [t0, t0+60] are used). Pure; no lookahead:
    it reads only in-window trades and never anything after t0+60. Byte-identical net-holding math to
    b20b.score, using token_amount; the reserve delta is used ONLY as a cross-check — a trade whose
    delta disagrees with its signed token_amount is DROPPED and the window's coverage reduced (an honest
    coverage loss instead of a silent concentration bias)."""
    window = _window(trades, t0_slot)
    dropped = 0
    validated = []
    for t in window:
        if t.reserve_delta_tokens is not None:
            signed = t.token_amount if t.is_buy else -t.token_amount
            if abs(t.reserve_delta_tokens - signed) > crosscheck_rounding_atoms:
                dropped += 1
                continue
        validated.append(t)

    buyers = {t.trader for t in validated if t.is_buy}
    if len(buyers) < MIN_BUYERS_TO_SCORE:
        return ScreenVerdict(UNREADABLE, False, 0, len(buyers), 0, len(validated), dropped,
                             shadow={"thin": True, "reason": "fewer_than_2_buyers"})

    held: dict[str, int] = {}
    for t in validated:
        held[t.trader] = held.get(t.trader, 0) + (t.token_amount if t.is_buy else -t.token_amount)
    total = sum(v for v in held.values() if v > 0)
    if total <= 0:
        return ScreenVerdict(NO_NET, False, 0, len(buyers), 0, len(validated), dropped,
                             shadow={"reason": "no_net_tokens_bought"})
    top = max(held.values())
    flagged = top * 100 >= total * CONCENTRATION_THRESHOLD          # identical integer compare to b20b
    top_share_bps = (top * 10000) // total

    # --- SHADOW footprint signals: computed, logged, NON-DECISIONAL ---
    shadow: dict = {}
    if dev_wallet:
        shadow["dev_share_bps"] = (max(0, held.get(dev_wallet, 0)) * 10000) // total
    # same-slot bundle: wallets whose only in-window buy is at t0 and who never re-trade in window
    first_buy_slot: dict[str, int] = {}
    trade_count: dict[str, int] = {}
    for t in validated:
        trade_count[t.trader] = trade_count.get(t.trader, 0) + 1
        if t.is_buy and t.trader not in first_buy_slot:
            first_buy_slot[t.trader] = t.slot
    bundle_wallets = [w for w, s in first_buy_slot.items()
                      if s == t0_slot and trade_count.get(w, 0) == 1 and held.get(w, 0) > 0]
    if len(bundle_wallets) >= 2:
        shadow["same_slot_share_bps"] = (sum(held[w] for w in bundle_wallets) * 10000) // total
        shadow["same_slot_wallets"] = len(bundle_wallets)

    status = VETO_CONCENTRATION if flagged else SURVIVED
    return ScreenVerdict(status, flagged, top_share_bps, len(buyers), total,
                         len(validated), dropped, shadow=shadow)
