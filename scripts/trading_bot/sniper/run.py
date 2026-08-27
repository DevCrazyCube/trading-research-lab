#!/usr/bin/env python3
"""Live PAPER runner for the sniper stack. Streams real-time pump.fun trades from the best healthy
DataProvider (Chainstack WS), aggregates 1s bars, and runs a POPULATION of exit-variants in PARALLEL
on the SAME entry signals (same surges, different exits) so FRESH forward data adjudicates which exit
policy is best — honest forward-selection, never retroactive tuning. Each variant keeps its own paper
ledger + scorecard. PAPER / DRY-RUN ONLY: nothing signs/sends, no wallet/key is ever loaded.

Diagnosed 2026-08-26 from 288 live trades: exit:trail leaked (-0.14R, 67% of trades) while exit:flow
was +0.29R. Variants convex_flowmain / convex_widetrail test de-emphasising the trail, forward.

MUST run under the websockets venv:
    scripts/trading_bot/memestream/.venv/bin/python -m scripts.trading_bot.sniper.run
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import statistics as st
import time

from .types import Bar
from .signals import SurgeDetector, PARAM_GRID
from .strategy import ConvexityStrategy, PRESETS
from .execution import DryRunExecutor
from . import paper_ledger

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "research", "data", "sniper_cache")
HEARTBEAT = os.path.join(os.path.dirname(__file__), "logs", "run.log")
SCORE_EVERY_S = 60.0
IDLE_PRUNE_S = 600.0
V3_PREREG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                        "research", "trading_bot", "SNIPER_V3_PREREGISTRATION.md"))
V3_PREREG_SHA256 = "ea486d591f426bfaec0c8d12a2d7e3b2a711405659b78d9e441582d76191e5e9"
# (ledger-name, exit-preset, entry-surge-config). The 903-trade eval showed exits are near-optimal
# (convex_core best; flow-exit +0.215R is the winner, trail is a loss-limiter) and the LEAK is on the
# ENTRY: 539 trail-exits are FADING surges that didn't sustain. So hold the winning exit fixed and
# forward-test ENTRY-strictness: BALANCED (baseline) vs TIGHT (stricter surge, should cut faders) vs
# WIDE (looser, to bracket). Fresh data adjudicates whether a stricter entry lifts the net.
# 4th field (optional) = use the on-chain RUG-RISK entry filter. core_rugfilter is core_bal's TWIN
# (same winning exits + BALANCED entry) that ADDITIONALLY declines entries when rug_score >= threshold.
# It runs in PARALLEL beside core_bal so fresh forward data adjudicates whether blocking the concentrated
# / bundled / liquidity-pulling launches CUTS the -1R catastrophe (rug) rate and LIFTS net mean R. See
# rugrisk.py. Read-only: the filter only reads chain + the tick stream, never signs/sends.
# CULLED 2026-08-26 (owner: "kill all useless sniper versions"). The entry-strictness question is
# ANSWERED forward: BALANCED (core_bal, -0.051R) BEAT both TIGHT (-0.090R, n=2055) and WIDE (-0.076R,
# n=989) -- a stricter OR looser surge gate made the bleed WORSE, not better. The rug-filter A/B is
# ANSWERED too: core_rugfilter (-0.056R, n=1339) did NOT beat its twin core_bal and did not cut the
# catastrophe rate -- the on-chain rug gate does not help. All three retired. core_bal stays as the
# single reference arm (and the ledger the rug-deployer cold-starts from). Their ledgers are kept on
# disk as the evidence; they simply stop trading. K for the family is unchanged (trials already ran).
VARIANT_SPECS = [
    # V3 starts after V2 exposed/fixed the reconnect-book reset. Legacy and V2 stay immutable evidence;
    # appending the stabilized runtime to either would mix distinct accounting regimes.
    ("v3_core_bal",       "convex_core", "BALANCED"),
    # core_confirm: core_bal's exact exits + BALANCED thresholds, but a 5s FOLLOW-THROUGH confirmation on
    # entry (the surge must sustain, not instantly fade). Added 2026-08-26 to attack the "small losers"
    # (fader surges that spike then die into a trail loss) by TIME-persistence -- distinct from core_tight
    # (a higher magnitude bar), which was tested and did WORSE. Forward data adjudicates whether waiting
    # for follow-through cuts the fader losses by more than it gives up entering a few seconds later.
    ("v3_core_confirm",   "convex_core", "CONFIRM"),
    # core_ratchet: core_bal's exact entry + a BREAKEVEN RATCHET exit (stop -> breakeven once +30%).
    # Added 2026-08-26 as the win-rate polish: converts winners-that-faded into breakevens instead of
    # trail losses, WITHOUT capping the fat tail. Exit-side complement to core_confirm's entry-side
    # fader filter; forward data adjudicates whether it lifts win rate + expectancy.
    ("v3_core_ratchet",   "convex_ratchet", "BALANCED"),
]


def _log(msg: str) -> None:
    line = f"{dt.datetime.now(dt.timezone.utc).isoformat()} {msg}"
    try:
        os.makedirs(os.path.dirname(HEARTBEAT), exist_ok=True)
        open(HEARTBEAT, "a").write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def _trades_path(preset: str) -> str:
    return os.path.join(OUT, f"live_trades_{preset}.jsonl")


def _score_path(preset: str) -> str:
    return os.path.join(OUT, f"live_scorecard_{preset}.json")


def _events_path(variant: str) -> str:
    return os.path.join(OUT, f"live_events_{variant}.jsonl")


class _BarAgg:
    """Aggregate live TradeTicks into completed per-mint 1s bars."""

    def __init__(self) -> None:
        self.cur: dict[str, dict] = {}
        self.venue: dict[str, str] = {}
        self.last_seen: dict[str, float] = {}

    def add(self, tick):
        mint = tick.mint
        sec = int(tick.ts)
        price = tick.price_usd
        if price is None or price <= 0:
            return None
        if tick.venue:
            self.venue[mint] = tick.venue
        self.last_seen[mint] = sec
        cur = self.cur.get(mint)
        done = None
        if cur is not None and cur["t"] != sec:
            done = (mint, self._finish(mint, cur)); cur = None
        if cur is None:
            cur = {"t": sec, "o": price, "h": price, "l": price, "c": price,
                   "v": 0.0, "buys": 0, "sells": 0, "buy_vol": 0.0, "sell_vol": 0.0}
            self.cur[mint] = cur
        cur["h"] = max(cur["h"], price); cur["l"] = min(cur["l"], price); cur["c"] = price
        cur["v"] += tick.usd
        if tick.side == "buy":
            cur["buys"] += 1; cur["buy_vol"] += tick.usd
        else:
            cur["sells"] += 1; cur["sell_vol"] += tick.usd
        return done

    def _finish(self, mint, b) -> Bar:
        return Bar(t=b["t"], o=b["o"], h=b["h"], l=b["l"], c=b["c"], v=b["v"], buys=b["buys"],
                   sells=b["sells"], buy_vol=b["buy_vol"], sell_vol=b["sell_vol"], dex=self.venue.get(mint))

    def prune(self, now_sec):
        for mint, seen in list(self.last_seen.items()):
            if now_sec - seen > IDLE_PRUNE_S:
                self.cur.pop(mint, None); self.last_seen.pop(mint, None)


class _Variant:
    """One (entry x exit) policy under test: its OWN detector (entry) + strategy (exits) + ledger.
    Giving each variant its own SurgeDetector lets us forward-test ENTRY-strictness too, not just exits."""

    def __init__(self, name: str, preset: str, surge_name: str, ex: DryRunExecutor,
                 rug=None) -> None:
        self.name = name                         # ledger key (may differ from preset)
        self.preset = preset
        self.strat = ConvexityStrategy(config=PRESETS.get(preset))
        self.det = SurgeDetector(config=(PARAM_GRID.get(surge_name) if surge_name else None))
        self.det.position_open = lambda m: m in self.open_mints
        self.ex = ex
        self.rug = rug                           # shared RugRiskScorer, or None (no filter)
        self.n_entries = 0
        self.n_rug_blocked = 0
        self.open_mints: set[str] = set()
        self.trades_path = _trades_path(name)
        self.events_path = _events_path(name)
        # Index ALL persisted entries by frozen_sha256 so a reopened position's entry is present and
        # resolves normally on close.
        self._entry_events: dict[str, dict] = {
            str(e.get("frozen_sha256")): e for e in paper_ledger.read_events(self.events_path)
            if e.get("kind") == "entry"
        }
        # Restore paper equity from the persisted (closed) ledger BEFORE reopening -- restore_equity_usd
        # requires an empty book.
        restored = paper_ledger.ledger_summary(self.events_path).get("adjudication_equity_usd")
        if restored is not None:
            self.strat.restore_equity_usd(restored)
        # RESTART-PROOF REOPEN (removes survivorship censoring): a prior process may have died with
        # persisted OPEN entries. Rather than charging each a full-loss restart gap (which biases the
        # resolved R-distribution toward trades that happened to close before a restart), reconstruct each
        # into the live book from its entry + latest checkpointed peak/flow mark, so it resolves against
        # live bars going forward exactly as if never restarted. Only genuinely unreconstructable entries
        # are still invalidated. Order matters: reload BEFORE invalidate, restore BEFORE reopen.
        self.reopened, failed = [], []
        for rec in paper_ledger.reload_open_entries(self.events_path):
            pos = self.strat.reopen_position(rec["entry"], rec["mark"])
            if pos is not None:
                self.open_mints.add(pos.mint); self.reopened.append(pos.frozen_sha256)
            else:
                failed.append(str(rec["entry"].get("frozen_sha256")))
        self.restart_invalidations = paper_ledger.invalidate_unresolved(self.events_path, only=set(failed))

    def step(self, mint: str, bar: Bar) -> None:
        # 1) exits on the open book
        for intent in self.strat.on_bar(mint, bar):
            fill = self.ex.execute(intent, liq_usd_per_s=max(1.0, bar.v))
            pos = self.strat.apply_fill(fill)
            if pos is not None and not pos.is_open:
                self.open_mints.discard(mint); self._write_resolution(pos)
        # 2) this variant's OWN entry signal
        sig = self.det.update(bar, mint=mint)
        if sig is not None and mint not in self.open_mints:
            # 2a) RUG-RISK filter (this variant only): decline concentrated / bundled launches. One
            #     cached RPC holder lookup per mint; fail-OPEN (allow + flag) if the coin can't be
            #     assessed, so missing data never halts trading.
            if self.rug is not None:
                assess = self.rug.rug_score(mint)
                if self.rug.blocks_entry(assess):
                    self.n_rug_blocked += 1
                    return
            intent = self.strat.on_signal(sig)
            if intent is not None:
                fill = self.ex.execute(intent, liq_usd_per_s=sig.liq_usd_per_s)
                pos = self.strat.apply_fill(fill)
                if pos is not None:
                    self._write_entry(pos, sig, intent)
                    self.open_mints.add(mint); self.n_entries += 1

    def sweep(self, now_ts: float) -> int:
        """Force-close positions past their wall-clock horizon (dead coins that stopped emitting bars),
        independent of the tick stream. Same exit/apply/write path as step()'s on_bar exits."""
        closed = 0
        for mint, intent in self.strat.sweep_stale(now_ts):
            fill = self.ex.execute(intent, liq_usd_per_s=1.0)   # thin-liquidity exit for a silent coin
            pos = self.strat.apply_fill(fill)
            if pos is not None and not pos.is_open:
                self.open_mints.discard(mint); self._write_resolution(pos); closed += 1
        return closed

    def checkpoint_open(self) -> None:
        """Append a position_mark for each OPEN position so a restart can REOPEN it honestly (peak/flow
        preserved). Called on the scorecard cadence; at most ~60s of new-high movement can be lost, and
        losing it only lowers the trail level -> conservative."""
        for pos in self.strat.open_positions():
            paper_ledger.append_event(
                self.events_path,
                paper_ledger.make_mark_event(variant=self.name, preset=self.preset, position=pos))

    def _write_entry(self, pos, sig, intent) -> None:
        frozen_utc = str(pos.meta["frozen_utc"])
        payload = self.strat.freeze_payload(intent, frozen_utc, sig)
        event = paper_ledger.make_entry_event(
            variant=self.name, preset=self.preset, position=pos, signal=sig,
            frozen_payload=payload, strategy_config=self.strat.cfg, executor=self.ex,
            experiment_sha256=V3_PREREG_SHA256)
        if not event["commitment_recomputable"]:
            raise RuntimeError(f"entry commitment mismatch for {pos.frozen_sha256}")
        paper_ledger.append_event(self.events_path, event)
        self._entry_events[pos.frozen_sha256] = event

    def _write_resolution(self, pos) -> None:
        entry = self._entry_events.get(pos.frozen_sha256)
        if entry is None:
            raise RuntimeError(f"resolution without persisted V2 entry {pos.frozen_sha256}")
        event = paper_ledger.make_resolution_event(
            variant=self.name, preset=self.preset, position=pos, entry_event=entry)
        paper_ledger.append_event(self.events_path, event)

    def scorecard(self) -> dict:
        led = paper_ledger.ledger_summary(self.events_path)
        rs = led["reported_r"]
        stress_rs = led["stress_r"]
        sc = {"variant": self.name, "preset": self.preset,
              "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "schema_version": 2, "n_resolved": led["terminal"], "n_priced": len(rs),
              "n_open": led["open"],
              "n_entries": self.n_entries, "rug_filter": self.rug is not None,
              "n_rug_blocked": self.n_rug_blocked,
              "restart_invalidations": led["restart_invalidations"],
              "stale_marks_full_loss_stressed": led["stale_mark_stressed"],
              "commitment_failures": led["commitment_failures"],
              "adjudication_equity_usd": led["adjudication_equity_usd"],
              "stress_realized_pnl_usd": led["stress_realized_pnl_usd"],
              "framing": ("LIVE PAPER V2 — dry-run, no orders/wallet. Primary adjudication is the "
                          "full-loss stress stream; <30 terminal entries = behaviour.")}
        if self.rug is not None:
            sc["rug_coverage"] = self.rug.coverage()
        if rs:
            w = [r for r in rs if r > 0]
            catastrophes = [r for r in rs if r <= -0.999]   # -1R rugs: the tail the filter targets
            sc.update(win_rate=round(len(w) / len(rs), 4), mean_R=round(st.mean(rs), 4),
                      median_R=round(st.median(rs), 4), sum_R=round(sum(rs), 3),
                      best_R=round(max(rs), 3), worst_R=round(min(rs), 3),
                      n_catastrophe=len(catastrophes),
                      catastrophe_rate=round(len(catastrophes) / len(rs), 4))
        if stress_rs:
            sc.update(stress_n=len(stress_rs), stress_mean_R=round(st.mean(stress_rs), 4),
                      stress_median_R=round(st.median(stress_rs), 4),
                      stress_sum_R=round(sum(stress_rs), 3),
                      adjudication="stress stream includes restart gaps and stale timeout marks as full loss")
        try:
            json.dump(sc, open(_score_path(self.name), "w"), indent=2)
        except OSError:
            pass
        return sc


def _load_persisted_r(path: str) -> list[float]:
    rs: list[float] = []
    try:
        for line in open(path):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line).get("realized_r")
            except ValueError:
                continue
            if r is not None:
                rs.append(float(r))
    except OSError:
        pass
    return rs


def _build_runtime(variants_spec=None):
    """Construct the paper book ONCE per OS process, not once per websocket connection."""
    try:
        actual_prereg = hashlib.sha256(open(V3_PREREG, "rb").read()).hexdigest()
    except OSError as exc:
        raise RuntimeError(f"V3 preregistration unavailable: {exc}") from exc
    if actual_prereg != V3_PREREG_SHA256:
        raise RuntimeError(f"V3 preregistration moved: expected {V3_PREREG_SHA256}, got {actual_prereg}")
    ex = DryRunExecutor()
    agg = _BarAgg()
    spec = variants_spec or VARIANT_SPECS
    # One SHARED rug scorer for every rug-filtered variant, so a candidate mint is looked up at most once
    # across variants (holder RPC is cached per-mint). Built only if some variant asks for the filter.
    rug = None
    if any(len(s) > 3 and s[3] for s in spec):
        from .rugrisk import RugRiskScorer
        rug = RugRiskScorer()
        ing = rug.deployers.ingest_ledger(_trades_path("core_bal"))  # cold-start: learn past outcomes
        _log(f"rug-filter ON: threshold={rug.cfg.block_threshold} "
             f"deployer_ingest={ing} weights=hc{rug.cfg.w_holder}/eb{rug.cfg.w_early}"
             f"/lt{rug.cfg.w_liquidity}/dep{rug.cfg.w_deployer}")
    variants = [_Variant(s[0], s[1], s[2], ex, rug=(rug if (len(s) > 3 and s[3]) else None))
                for s in spec]
    _log(f"paper runtime initialized: variants={[v.name for v in variants]} "
         f"restart_invalidations={sum(len(v.restart_invalidations) for v in variants)}")
    return {"agg": agg, "rug": rug, "variants": variants}


def run(variants_spec=None, *, runtime=None):
    from .data import pick_provider
    runtime = runtime or _build_runtime(variants_spec)
    agg, rug, variants = runtime["agg"], runtime["rug"], runtime["variants"]
    provider = pick_provider()
    _log(f"provider = {getattr(provider, 'name', provider.__class__.__name__)} (healthy={provider.healthy()})")

    n_seen = 0
    last_score = time.monotonic()
    _log(f"live forward-selection start: variants={[v.name for v in variants]}")
    for tick in provider.stream_ticks():
        n_seen += 1
        if rug is not None:
            rug.observe_tick(tick)     # feed early-buyer / liquidity / deployer state (no RPC)
        done = agg.add(tick)
        if done is not None:
            mint, bar = done
            for v in variants:            # each variant runs its OWN entry detector + exits
                v.step(mint, bar)
        now = time.monotonic()
        if now - last_score >= SCORE_EVERY_S:
            agg.prune(time.time())
            if rug is not None:
                rug.prune(time.time())
            # Off-bar horizon enforcement: close dead coins that stopped emitting bars so the open book
            # can't grow without bound (the "156 open for hours" pathology). Wall-clock, every cycle.
            swept = sum(v.sweep(time.time()) for v in variants)
            if swept:
                _log(f"stale-sweep closed {swept} position(s) past max-hold horizon")
            for v in variants:            # checkpoint open peak/flow so a restart reopens, never censors
                v.checkpoint_open()
            cards = [v.scorecard() for v in variants]
            summary = "  ".join(
                f"{c['variant']}:n{c['n_resolved']}/stress{c.get('stress_mean_R')}" for c in cards)
            if rug is not None:
                cov = rug.coverage()
                blk = sum(v.n_rug_blocked for v in variants)
                summary += f"  [rug cov={cov['coverage_rate']} blocked={blk} rpc={cov['rpc_calls']}]"
            _log(f"ticks={n_seen}  {summary}")
            last_score = now
    return runtime


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.parse_args(argv)
    # Preserve positions/peak/flow state across ordinary provider reconnects.  Only a true process
    # restart rebuilds the runtime and invokes the append-only restart invalidation policy.
    runtime = _build_runtime()
    while True:
        try:
            run(runtime=runtime)
        except KeyboardInterrupt:
            return 0
        except Exception as e:  # noqa: BLE001 — a stream drop must not kill the loop
            _log(f"stream error: {repr(e)[:160]} -- reconnecting in 5s; paper book preserved")
            time.sleep(5.0)


if __name__ == "__main__":
    raise SystemExit(main())
