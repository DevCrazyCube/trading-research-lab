#!/usr/bin/env python3
"""strategy.py — the CONVEXITY trading policy + risk / bankroll module (agent C).

PAPER / DRY-RUN ONLY. This module never loads a wallet, never reads a key, never signs or sends a
transaction. It only turns `EntrySignal`s + `Bar`s into `OrderIntent`s and bookkeeps paper `Position`s.
Fill prices/costs come from the Executor; this module only decides *whether*, *how big*, and *when to
exit*, and computes R against the entry's risk unit. See ARCHITECTURE.md.

-------------------------------------------------------------------------------------------------------
WHY THIS SHAPE (the research rationale — do NOT "improve" it into a normal stop/target strategy):

Our research found exactly ONE structure with positive *gross* edge on liquid memecoins:
momentum-surge entry -> LET WINNERS RUN (uncapped) -> exit on flow-reversal / trailing give-back ->
wide catastrophe backstop, sized by fractional / inverse-vol bankroll discipline across MANY concurrent
uncorrelated positions.

  * NO TIGHT PRICE TARGET. A capped target (e.g. +30%, +50%) threw the edge away. The return
    distribution here is heavily right-skewed / convex: a small number of trades run 3x-20x and pay for
    a large number of small losers. Capping the top truncates exactly the fat right tail that IS the
    edge. Expectancy is carried by the rare monster, so we must let winners run.

  * NO TIGHT PRICE STOP. A tight stop looks safe but is a trap on these names: price gaps THROUGH a
    tight stop (1s bars, thin books) so the realized loss overshoots the stop anyway, AND a tight stop
    knifes you out of names that wiggle -40% intrabar and then go 10x. Tight stops converted winners
    into losers and did not even bound the loss they promised. So the only price-based backstop is WIDE
    (a catastrophe line, -50%..-70%), sized so that hitting it is the definition of -1R, not a
    frequent event.

  * EXIT ON FLOW, NOT PRICE. The honest signal that a pump is over is buy-pressure flipping to sell
    pressure (the 1s buy-volume fraction collapsing), not a price threshold. HONEST CAVEAT (baked in
    below): research showed the flow-flip LAGS the actual dump — by the time buys dry up for k seconds,
    price has already given back. So flow-exit ALONE is not enough; we ALSO run a trailing give-back
    exit that locks in the run-up the flow-flip is too slow to catch. The two are complementary:
    trailing catches the fast rug, flow catches the slow bleed where price drifts but never trips the
    trail.

  * CONSISTENCY COMES FROM DIVERSIFICATION, NOT FROM ANY SINGLE TRADE. Each bet is a small fraction of
    bankroll; many uncorrelated positions run at once; per-trade size SHRINKS as gross exposure grows
    so no cluster of correlated pumps can dominate the book. The convexity is per-trade; the smoothness
    is portfolio-level. That is the only place the "reliability" the owner wants can come from with a
    right-skewed edge — you cannot make a single memecoin bet reliable, you can only make the *ensemble*
    reliable by keeping every bet small and running a lot of them.

DETERMINISTIC: no RNG, no hidden state beyond the book. The only wall-clock touch is the entry-freeze
UTC stamp, and that is injectable (a `clock`) so tests are fully reproducible.
-------------------------------------------------------------------------------------------------------
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Callable, Optional

# Import the shared contracts. NOTE: this module is named `strategy`, the stdlib module is `types`;
# the shared contract lives in THIS package's `types.py`, so import it by package-relative path when
# run as a package, else fall back to a direct import when run as a loose script (selftest).
try:  # package context (run.py: `from .strategy import ...`)
    from .types import (
        Bar,
        EntrySignal,
        Fill,
        OrderIntent,
        Position,
    )
except ImportError:  # loose-script context (selftest / ad-hoc): load the sibling types.py by path.
    # We do NOT `from types import ...` here — stdlib `types` is almost always already cached in
    # sys.modules and would shadow the local file. Load the sibling contract explicitly instead.
    import importlib.util as _ilu
    import os as _os
    import sys as _sys

    _tp = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "types.py")
    _mod = _sys.modules.get("_sniper_types")
    if _mod is None:
        _spec = _ilu.spec_from_file_location("_sniper_types", _tp)
        _mod = _ilu.module_from_spec(_spec)
        # register before exec: dataclasses resolves cls.__module__ via sys.modules.
        _sys.modules["_sniper_types"] = _mod
        _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
    Bar = _mod.Bar
    EntrySignal = _mod.EntrySignal
    Fill = _mod.Fill
    OrderIntent = _mod.OrderIntent
    Position = _mod.Position


# ============================== configuration ==============================
@dataclass(frozen=True)
class ConvexityConfig:
    """All policy knobs. Presets below give a few DIVERSE settings for later forward-selection.

    Every size is USD paper notional.  The old ``bankroll=10`` configuration was unit-ambiguous while
    ``OrderIntent.usd_size`` and ``Fill.usd_size`` were explicitly USD.  In production-like paper runs
    that silently turned a nominal 2% bet into $0.20 (often $0.10 after inverse-vol scaling), even though
    the fixed round-trip priority-fee estimate alone was about $0.075.  V2 therefore pins the account and
    minimum order in USD and sizes from CURRENT paper equity rather than a never-changing start balance.
    """
    name: str = "convex_core"

    # --- bankroll / sizing discipline ---
    initial_bankroll_usd: float = 1000.0   # explicit USD paper account; never a wallet balance
    max_frac_per_trade: float = 0.02       # <=2% of bankroll as the base per-trade size
    max_concurrent_positions: int = 25     # cap on simultaneously-open positions
    max_gross_exposure_frac: float = 0.50  # deploy at most 50% of bankroll at once (dry powder always)
    one_position_per_mint: bool = True     # never stack the same mint
    min_trade_notional: float = 2.0        # refuse dust whose fixed costs dominate the experiment
    allowed_venues: tuple[str, ...] = ("pumpfun",)  # PLAN initial regime: Pump bonding curve only

    # inverse-vol scaling: shrink size when the surge is unusually violent (proxy for realized vol),
    # grow (bounded) when it is mild. Signal has no vol field, so surge_bps is the vol proxy.
    inverse_vol: bool = True
    vol_ref_bps: float = 300.0             # "normal" surge; scale = vol_ref / surge
    vol_scale_lo: float = 0.50             # never shrink below 0.5x base ...
    vol_scale_hi: float = 1.50             # ... nor grow above 1.5x base

    # --- LET-WINNERS-RUN convexity exits ---
    trail_bps: float = 3500.0              # trailing give-back from peak (35%). WIDE on purpose.
    flow_exit_frac: float = 0.45           # exit if 1s buy-vol fraction sits below this ...
    flow_exit_k: int = 5                   # ... for this many CONSECUTIVE seconds (after min hold)
    min_hold_s: int = 20                   # don't act on flow noise before this many seconds
    catastrophe_frac: float = 0.60         # WIDE backstop: exit if price is <= entry*(1-0.60) => -60%
    max_hold_s: int = 1800                 # final horizon cap (30 min) for a stagnant position
    # BREAKEVEN RATCHET (default OFF). Once a position has printed a peak gain >= breakeven_arm_frac,
    # protect it: if price then falls back to ~breakeven, exit FLAT rather than letting a position that
    # was clearly winning decay into a loss. Lifts win rate by converting faders-that-first-ran into
    # breakevens, WITHOUT capping the fat tail — a deep runner is stopped by the WIDE trail (far above
    # breakeven) long before it could retrace all the way to entry. breakeven_cushion covers the toll so
    # a "breakeven" exit is truly net-flat, not a small loss.
    breakeven_arm_frac: float = 0.0        # arm once peak >= entry*(1+this); 0 = ratchet disabled
    breakeven_cushion_bps: float = 300.0   # breakeven exit level = entry*(1+this) (covers round-trip toll)

    def risk_unit(self, entry_price: float) -> float:
        """The entry's risk unit = distance to the catastrophe backstop. Hitting catastrophe == -1R.
        R is measured against THIS, so a runner that 4x's is a large positive R and the convexity of the
        edge is visible in the R distribution."""
        return entry_price * self.catastrophe_frac


# A few diverse presets. These are NOT tuned to observed outcomes — they are deliberately spread so a
# later forward-selection pass (sim.py) can pick, out of sample, without us peeking.
PRESETS: dict[str, ConvexityConfig] = {
    # balanced middle-of-the-road convexity
    "convex_core": ConvexityConfig(name="convex_core"),
    # let winners run even harder: wider trail, wider catastrophe, longer horizon, slower flow trigger
    "convex_wide": ConvexityConfig(
        name="convex_wide",
        max_frac_per_trade=0.015,
        max_concurrent_positions=40,
        trail_bps=5000.0,
        flow_exit_frac=0.40,
        flow_exit_k=8,
        min_hold_s=30,
        catastrophe_frac=0.70,
        max_hold_s=3600,
    ),
    # quicker to react on flow (but STILL no tight price target/stop): tighter trail + faster flow flip
    "convex_tight_flow": ConvexityConfig(
        name="convex_tight_flow",
        max_frac_per_trade=0.025,
        max_concurrent_positions=20,
        trail_bps=2500.0,
        flow_exit_frac=0.50,
        flow_exit_k=3,
        min_hold_s=15,
        catastrophe_frac=0.50,
        max_hold_s=900,
    ),
    # --- DIAGNOSED variants (2026-08-26, from 288 live trades) ---------------------------------------
    # Live diagnosis: exit:trail leaked (-0.14R over 67% of trades, sum -27R) while exit:flow was
    # POSITIVE (+0.29R, sum +24R). Hypothesis: the 35% trail cuts non-runners at a small loss; let the
    # flow-reversal exit do the work instead. These two test that FORWARD (fresh data adjudicates).
    "convex_flowmain": ConvexityConfig(   # trail effectively OFF (90%) -> flow + catastrophe drive exits
        name="convex_flowmain",
        trail_bps=9000.0,
        flow_exit_frac=0.45,
        flow_exit_k=5,
        min_hold_s=20,
        catastrophe_frac=0.60,
        max_hold_s=1800,
    ),
    "convex_widetrail": ConvexityConfig(  # trail only fires on a REAL 60% give-back from a high peak
        name="convex_widetrail",
        trail_bps=6000.0,
        flow_exit_frac=0.45,
        flow_exit_k=5,
        min_hold_s=20,
        catastrophe_frac=0.60,
        max_hold_s=1800,
    ),
    # --- WIN-RATE POLISH (2026-08-26): convex_core + a BREAKEVEN RATCHET. Once a position has printed
    # >= +30%, its stop moves to breakeven, so a winner-that-faded books ~0R instead of a trail loss.
    # Everything else identical to convex_core, so this isolates the ratchet's effect. Preserves the fat
    # tail (a deep runner trips the wide 35% trail far above breakeven). Forward data adjudicates.
    "convex_ratchet": ConvexityConfig(
        name="convex_ratchet",
        breakeven_arm_frac=0.30,
        breakeven_cushion_bps=300.0,
    ),
}


def get_preset(name: str) -> ConvexityConfig:
    if name not in PRESETS:
        raise KeyError(f"unknown preset {name!r}; have {sorted(PRESETS)}")
    return PRESETS[name]


# ============================== the strategy ==============================
_EXIT_PRIORITY = ("breakeven", "catastrophe", "trail", "flow", "maxhold")


class ConvexityStrategy:
    """Implements the `Strategy` Protocol (on_signal, on_bar) plus fill bookkeeping + book views.

    Lifecycle (driven by run.py):
        sig  -> on_signal(sig)        -> OrderIntent(buy,"entry") or None   [frozen here]
        fill -> apply_fill(entry_fill)-> opens a Position
        bar  -> on_bar(mint, bar)     -> [OrderIntent(sell,"exit:<reason>")] when a rule fires
        fill -> apply_fill(exit_fill) -> closes the Position, computes realized R

    The Protocol only mandates on_signal / on_bar. `apply_fill`, `open_positions`, `book_summary` are the
    extra surface run.py / sim.py use to feed executor fills back in and read the scorecard.
    """

    def __init__(self, config: Optional[ConvexityConfig] = None,
                 clock: Optional[Callable[[], datetime]] = None) -> None:
        self.cfg = config or PRESETS["convex_core"]
        # injectable clock ONLY for the freeze stamp (keeps the policy deterministic + tests reproducible)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

        self._open: dict[str, Position] = {}      # mint -> open Position (one per mint)
        self._closed: list[Position] = []          # closed Positions, in close order
        # entries frozen at signal time, awaiting their entry fill: mint -> pending record
        self._pending: dict[str, dict] = {}
        self._equity_usd = float(self.cfg.initial_bankroll_usd)

    # ------------------------------ ENTRY ------------------------------
    def on_signal(self, sig: EntrySignal) -> Optional[OrderIntent]:
        """Decide whether/how to open, sized by bankroll discipline. Refuse (return None) if any limit
        is hit. Freeze the intent (sha256 + UTC) BEFORE the outcome is known."""
        c = self.cfg

        # --- hard refusals: per-mint cap, concurrency cap ---
        if c.one_position_per_mint and (sig.mint in self._open or sig.mint in self._pending):
            return None
        if len(self._open) + len(self._pending) >= c.max_concurrent_positions:
            return None
        venue = (sig.venue or "").strip().lower().replace(".", "")
        allowed = {v.strip().lower().replace(".", "") for v in c.allowed_venues}
        if not venue or venue not in allowed:
            return None

        # --- exposure budget: never deploy more than max_gross_exposure_frac of bankroll ---
        gross_budget = self._equity_usd * c.max_gross_exposure_frac
        remaining = gross_budget - self._gross_exposure()
        if remaining <= 0:
            return None

        # --- base fractional size, then inverse-vol scaling, then clamp to remaining budget ---
        base = self._equity_usd * c.max_frac_per_trade
        scale = self._vol_scale(sig.surge_bps)
        size = base * scale
        # SHRINK as the book fills: never exceed the remaining gross budget. This is what makes size
        # decay as concurrent exposure grows — the diversification discipline.
        if size > remaining:
            size = remaining
        if size < c.min_trade_notional:
            return None
        size = round(size, 9)

        intent = OrderIntent(
            mint=sig.mint,
            side="buy",
            ts=sig.ts,
            ref_price_usd=sig.ref_price_usd,
            usd_size=size,
            venue=sig.venue,
            tag="entry",
        )

        # --- FREEZE before outcome: sha256 over the canonical intent + the UTC stamp ---
        frozen_utc = self._clock().astimezone(timezone.utc).isoformat()
        frozen = self._freeze(intent, frozen_utc, sig)
        self._pending[sig.mint] = {
            "intent": intent,
            "frozen_sha256": frozen,
            "frozen_utc": frozen_utc,
            "sig": sig,
        }
        return intent

    # ------------------------------ FILL BOOKKEEPING ------------------------------
    def apply_fill(self, fill: Fill) -> Optional[Position]:
        """Route an executor fill: a buy opens the pending Position; a sell closes the open one and
        computes realized R vs the entry's risk unit. Returns the affected Position (or None)."""
        if fill.side == "buy":
            return self._open_position(fill)
        if fill.side == "sell":
            return self._close_position(fill)
        return None

    def _open_position(self, fill: Fill) -> Optional[Position]:
        pend = self._pending.pop(fill.mint, None)
        if pend is None:
            # no frozen entry for this mint (shouldn't happen in-flow); ignore defensively
            return None
        if self.cfg.one_position_per_mint and fill.mint in self._open:
            return None
        pos = Position(
            mint=fill.mint,
            entry=fill,
            venue=pend["intent"].venue,
            peak_price=fill.price_usd,
            opened_ts=fill.ts,
            frozen_sha256=pend["frozen_sha256"],
            meta={
                "frozen_utc": pend["frozen_utc"],
                "risk_unit": self.cfg.risk_unit(fill.price_usd),
                "flow_below_streak": 0,
                "exit_sent": False,
                "sig_reason": pend["sig"].reason,
                "equity_usd_at_entry": self._equity_usd,
            },
        )
        self._open[fill.mint] = pos
        return pos

    def reopen_position(self, entry_event: dict, mark: dict | None = None) -> Optional[Position]:
        """Reconstruct an OPEN Position from its persisted entry event (+ latest position_mark) after a
        process restart, so it resolves against live bars going forward instead of being censored/charged
        a full-loss restart gap. Idempotent; mirrors _open_position's meta shape. Does NOT touch _pending,
        _closed or _equity_usd (equity is restored separately, before reopen). Returns the Position, or
        None if it cannot be honestly rebuilt (malformed fill, or the mint is already open)."""
        try:
            fill = Fill(**entry_event["entry_fill"])
        except (TypeError, KeyError, ValueError):
            return None
        if fill.price_usd <= 0 or (self.cfg.one_position_per_mint and fill.mint in self._open):
            return None
        peak = float(mark["peak_price"]) if mark and mark.get("peak_price") is not None else fill.price_usd
        streak = int(mark["flow_below_streak"]) if mark and mark.get("flow_below_streak") is not None else 0
        frozen_utc = (entry_event.get("frozen_payload") or {}).get("frozen_utc")
        sig_reason = (entry_event.get("signal") or {}).get("reason")
        pos = Position(
            mint=fill.mint,
            entry=fill,
            venue=entry_event.get("venue"),
            peak_price=peak,
            opened_ts=fill.ts,
            frozen_sha256=entry_event.get("frozen_sha256", ""),
            meta={
                "frozen_utc": frozen_utc,
                "risk_unit": self.cfg.risk_unit(fill.price_usd),   # recomputed, deterministic from entry
                "flow_below_streak": streak,
                "exit_sent": False,
                "sig_reason": sig_reason,
                "equity_usd_at_entry": entry_event.get("equity_usd_at_entry"),
                "last_price": (mark or {}).get("last_price"),
                "last_bar_ts": (mark or {}).get("last_bar_ts"),
                "reopened": True,
            },
        )
        self._open[fill.mint] = pos
        return pos

    def _close_position(self, fill: Fill) -> Optional[Position]:
        pos = self._open.pop(fill.mint, None)
        if pos is None:
            return None
        risk_unit = pos.meta.get("risk_unit") or self.cfg.risk_unit(pos.entry.price_usd)
        entry = pos.entry
        # NET realized R: the price move MINUS the round-trip venue toll and the priority tips. The
        # executor reports these on each Fill (toll_bps per side, tip_usd absolute) but they were
        # previously dropped, so R was slippage-net but toll-GROSS -- flattering every result by ~one
        # round-trip toll. Subtract them as a per-UNIT price cost so R is honestly net of all frictions.
        gross = fill.price_usd - entry.price_usd
        toll_cost = (entry.toll_bps + fill.toll_bps) / 10_000.0 * entry.price_usd   # round-trip toll
        units = (entry.usd_size / entry.price_usd) if entry.price_usd > 0 else 0.0
        tip_cost = ((entry.tip_usd + fill.tip_usd) / units) if units > 0 else 0.0   # tips, per unit
        realized_r = (gross - toll_cost - tip_cost) / risk_unit if risk_unit else 0.0
        units = (entry.usd_size / entry.price_usd) if entry.price_usd > 0 else 0.0
        realized_pnl_usd = realized_r * risk_unit * units
        equity_before = self._equity_usd
        self._equity_usd = max(0.0, self._equity_usd + realized_pnl_usd)
        pos.exit = fill
        # exit_reason was stamped on the position when the intent fired; keep it if present
        pos.exit_reason = pos.exit_reason or pos.meta.get("pending_exit_reason", "")
        pos.realized_r = realized_r
        pos.meta["realized_pnl_usd"] = realized_pnl_usd
        pos.meta["equity_usd_before_exit"] = equity_before
        pos.meta["equity_usd_after_exit"] = self._equity_usd
        self._closed.append(pos)
        return pos

    # ------------------------------ EXITS ------------------------------
    def on_bar(self, mint: str, bar: Bar) -> list[OrderIntent]:
        """Per-bar update for the open position on `mint`. Updates the peak, then checks the convexity
        exit rules in priority order and emits at most one exit intent."""
        pos = self._open.get(mint)
        if pos is None or not pos.is_open:
            return []
        if pos.meta.get("exit_sent"):
            return []  # already emitted an exit intent; wait for the exit fill

        # LET WINNERS RUN: track the peak every bar (uncapped — no target ever caps this).
        if bar.h > pos.peak_price:
            pos.peak_price = bar.h
        # Track the last observed close so an off-bar stale sweep can mark honestly at a real price.
        pos.meta["last_price"] = bar.c
        pos.meta["last_bar_ts"] = bar.t

        reason, trigger_price = self._eval_exits(pos, bar)
        if reason is None:
            return []

        pos.meta["exit_sent"] = True
        pos.exit_reason = f"exit:{reason}"
        pos.meta["pending_exit_reason"] = f"exit:{reason}"
        # A threshold is not a guaranteed fill.  If the completed bar already closed through the stop
        # or trail, price the paper sell at the WORSE observed close instead of the flattering trigger.
        # (Flow/max-hold already return the close, so min() is a no-op for those exits.)
        executable_mark = min(trigger_price, bar.c) if bar.c > 0 else trigger_price
        return [OrderIntent(
            mint=mint,
            side="sell",
            ts=float(bar.t),
            ref_price_usd=executable_mark,
            usd_size=pos.entry.usd_size,
            venue=pos.venue,
            tag=f"exit:{reason}",
        )]

    def _eval_exits(self, pos: Position, bar: Bar) -> tuple[Optional[str], float]:
        """Return (reason, trigger_price) for the first-firing rule, else (None, 0). Priority order:
        catastrophe (deep gap-through) -> trailing give-back -> flow reversal -> max-hold horizon."""
        c = self.cfg
        entry_price = pos.entry.price_usd
        held_s = bar.t - pos.opened_ts

        # 0) BREAKEVEN RATCHET (highest priority when armed): once the peak printed >= entry*(1+arm), a
        #    fall back to ~breakeven exits FLAT instead of decaying into a loss. Sits above the trail
        #    because its level (~breakeven) is HIGHER than the trail level for a shallow runner, so a
        #    position that ran then fully retraced is booked at breakeven, not at the trail's loss. A
        #    deep runner never reaches here: its wide trail (peak*0.65) trips far above breakeven first.
        if c.breakeven_arm_frac > 0.0:
            arm_level = entry_price * (1.0 + c.breakeven_arm_frac)
            be_level = entry_price * (1.0 + c.breakeven_cushion_bps / 10_000.0)
            if pos.peak_price >= arm_level and bar.l <= be_level:
                return "breakeven", be_level

        # 1) WIDE CATASTROPHE backstop (NOT a tight stop). A bar low at/below entry*(1-frac) means the
        #    name gapped straight through everything — this is the -1R backstop and it takes priority so
        #    a true crash is labeled honestly as a catastrophe, not a "trail".
        cat_level = entry_price * (1.0 - c.catastrophe_frac)
        if bar.l <= cat_level:
            return "catastrophe", cat_level

        # 2) TRAILING give-back from the peak (locks the run-up; catches the fast rug the flow-flip is
        #    too slow to see). Wide trail => winners still run; only a real reversal off the top trips it.
        trail_level = pos.peak_price * (1.0 - c.trail_bps / 10_000.0)
        if bar.l <= trail_level:
            return "trail", trail_level

        # 3) FLOW REVERSAL: buy-pressure flipped. Count CONSECUTIVE seconds with buy-vol fraction below
        #    the floor, but only after the min hold (ignore early flow noise).
        #    HONEST CAVEAT: this LAGS the dump; that is exactly why (2) the trailing exit also runs. When
        #    a pump bleeds slowly (price drifts but never trips the wide trail) THIS is what gets us out.
        denom = bar.buy_vol + bar.sell_vol
        buy_frac = (bar.buy_vol / denom) if denom > 0 else 1.0  # no flow => treat as not-reversing
        if held_s >= c.min_hold_s and buy_frac < c.flow_exit_frac:
            pos.meta["flow_below_streak"] = int(pos.meta.get("flow_below_streak", 0)) + 1
        else:
            pos.meta["flow_below_streak"] = 0
        if pos.meta["flow_below_streak"] >= c.flow_exit_k:
            return "flow", bar.c

        # 4) MAX-HOLD horizon: a stagnant position that never ran and never crashed still gets capped.
        if held_s >= c.max_hold_s:
            return "maxhold", bar.c

        return None, 0.0

    # ------------------------------ sizing helpers ------------------------------
    def _vol_scale(self, surge_bps: float) -> float:
        """Inverse-vol scaling factor in [vol_scale_lo, vol_scale_hi]. Bigger surge (proxy for higher
        realized vol / a more extended move) => smaller size."""
        c = self.cfg
        if not c.inverse_vol:
            return 1.0
        s = max(surge_bps, 1.0)
        scale = c.vol_ref_bps / s
        return max(c.vol_scale_lo, min(c.vol_scale_hi, scale))

    def _gross_exposure(self) -> float:
        """Notional currently deployed: open positions + frozen-but-unfilled pending entries."""
        opened = sum(p.entry.usd_size for p in self._open.values())
        pending = sum(pd["intent"].usd_size for pd in self._pending.values())
        return opened + pending

    @staticmethod
    def freeze_payload(intent: OrderIntent, frozen_utc: str, sig: EntrySignal) -> dict:
        """Canonical entry commitment payload retained by the V2 event ledger."""
        return {
            "mint": intent.mint,
            "side": intent.side,
            "ts": intent.ts,
            "ref_price_usd": intent.ref_price_usd,
            "usd_size": intent.usd_size,
            "venue": intent.venue,
            "tag": intent.tag,
            "frozen_utc": frozen_utc,
            "sig_reason": sig.reason,
            "sig_surge_bps": sig.surge_bps,
        }

    @staticmethod
    def _freeze(intent: OrderIntent, frozen_utc: str, sig: EntrySignal) -> str:
        payload = ConvexityStrategy.freeze_payload(intent, frozen_utc, sig)
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(blob).hexdigest()

    # ------------------------------ off-bar stale sweep ------------------------------
    def sweep_stale(self, now_ts: float) -> list[tuple[str, OrderIntent]]:
        """Force-close positions past the max-hold horizon by WALL-CLOCK age, independent of bars.

        WHY: on_bar's max-hold can only fire when a fresh bar arrives for the mint. A memecoin that
        stops trading emits no bars, so its position would hang open FOREVER (the "156 open, held for
        hours" pathology). A silent coin has no current executable quote, so V2 adjudicates it at zero
        recovery rather than pretending the stale last trade is sellable.  The event ledger labels that
        mark non-executable and the equity curve carries the same full-loss bound. Mirrors on_bar's
        one-exit-per-position discipline (respects exit_sent).
        Returns (mint, sell-intent) pairs for the caller to execute exactly like an on_bar exit.
        """
        out: list[tuple[str, OrderIntent]] = []
        for mint, pos in list(self._open.items()):
            if not pos.is_open or pos.meta.get("exit_sent"):
                continue
            if now_ts - pos.opened_ts < self.cfg.max_hold_s:
                continue
            mark = 0.0
            pos.meta["exit_sent"] = True
            pos.exit_reason = "exit:maxhold_timeout"
            pos.meta["pending_exit_reason"] = "exit:maxhold_timeout"
            out.append((mint, OrderIntent(
                mint=mint, side="sell", ts=float(now_ts), ref_price_usd=float(mark),
                usd_size=pos.entry.usd_size, venue=pos.venue, tag="exit:maxhold_timeout")))
        return out

    # ------------------------------ book views ------------------------------
    def open_positions(self) -> list[Position]:
        return list(self._open.values())

    def restore_equity_usd(self, equity_usd: float) -> None:
        """Restore terminal adjudication equity before a new V2 process accepts signals."""
        if self._open or self._pending or self._closed:
            raise RuntimeError("equity restore is only valid on a fresh strategy instance")
        if equity_usd < 0:
            raise ValueError("equity cannot be negative")
        self._equity_usd = float(equity_usd)

    def closed_positions(self) -> list[Position]:
        return list(self._closed)

    def book_summary(self) -> dict:
        rs = [p.realized_r for p in self._closed if p.realized_r is not None]
        rs_sorted = sorted(rs)
        n = len(rs_sorted)
        mean_r = sum(rs_sorted) / n if n else 0.0
        median_r = (rs_sorted[n // 2] if n % 2 else (rs_sorted[n // 2 - 1] + rs_sorted[n // 2]) / 2) if n else 0.0
        wins = sum(1 for r in rs if r > 0)
        by_reason: dict[str, int] = {}
        for p in self._closed:
            by_reason[p.exit_reason] = by_reason.get(p.exit_reason, 0) + 1
        return {
            "preset": self.cfg.name,
            "initial_bankroll_usd": self.cfg.initial_bankroll_usd,
            "equity_usd": self._equity_usd,
            "open": len(self._open),
            "pending": len(self._pending),
            "closed": n,
            "gross_exposure": round(self._gross_exposure(), 9),
            "gross_budget": round(self._equity_usd * self.cfg.max_gross_exposure_frac, 9),
            "win_rate": (wins / n) if n else 0.0,
            "mean_r": mean_r,
            "median_r": median_r,
            "max_r": max(rs) if rs else 0.0,
            "min_r": min(rs) if rs else 0.0,
            "sum_r": sum(rs),
            "exits_by_reason": by_reason,
        }


# convenience factory
def build_strategy(preset: str = "convex_core",
                   clock: Optional[Callable[[], datetime]] = None,
                   **overrides) -> ConvexityStrategy:
    cfg = get_preset(preset)
    if overrides:
        cfg = replace(cfg, **overrides)
    return ConvexityStrategy(cfg, clock=clock)
