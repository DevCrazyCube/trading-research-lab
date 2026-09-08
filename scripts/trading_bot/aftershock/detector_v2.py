#!/usr/bin/env python3
"""AFTERSHOCK V2 detector — PAYABLE ABSORPTION. PAPER, read-only, event-driven.

V2 keeps V1's WATCH -> ARMED state machine but replaces GROSS-buy absorption with NET RESERVE
REPLACEMENT and adds an entry-veto and a stabilization window. V1's `detector.py` is imported and left
byte-identical; every V2 gate is additive here (an improvement is a NEW instrument, never an edit).

The V2 entry (frozen AFTERSHOCK_V2_PREREGISTRATION.md) fires PASS only when ALL hold:
  1. material cluster dump (V1 arm gate);
  2. NetReplacementRatio (Rt - Rmin) / S >= net_replacement_ratio_min  (NET refill, not gross churn);
  3. full recovery Rt >= R0  (capacity_recover_frac = 1.0 via the frozen spec; V1 used 0.9);
  4. >= min new independent buyers (V1);
  5. B20B pass k60 < k60_max (V1);
  6. coverage >= entry floor for the full position (V1);
  7. entry-veto: no exit condition already true at the fire instant (flow-veto is the arm-B/C strict gate);
  8. stabilization: over the final stabilization window, net reserve flow is non-declining and no cluster
     wallet resumes selling.

Rmin (the post-shock trough) and R0 (= r_pre) are exact external-SOL reads from the ECR kernel. The
accumulation window (absorption_window_slots) and the evaluation instant (absorption + stabilization)
are decoupled so absorption is measured over the first phase and stabilization over the second.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import ecr
from .detector import DetectorConfig, Detector, _MintDetector, SLOT_SECONDS


@dataclass(frozen=True)
class DetectorV2Config(DetectorConfig):
    # NET replacement + stabilization (V2 additions; capacity_recover_frac comes from the frozen spec = 1.0)
    net_replacement_ratio_min: float = 1.0
    stabilization_window_slots: int = 15
    stabilization_requires_positive_net_reserve_flow: bool = True
    # Entry-veto flow window (mirrors the exit FLOW_FLIP test); strict only for arms B/C.
    veto_strict: bool = False
    flow_flip_sell_frac: float = 0.65
    flow_window_slots: int = 60
    flow_min_window_sol: float = 0.1
    flow_min_trades: int = 3

    @classmethod
    def from_spec(cls, spec: dict, *, veto_strict: bool) -> "DetectorV2Config":
        det = dict(spec["detector"])
        ex = spec.get("exit", {})
        kw = {k: det[k] for k in det if k in cls.__dataclass_fields__}
        kw["veto_strict"] = veto_strict
        for k in ("flow_flip_sell_frac", "flow_window_slots", "flow_min_window_sol", "flow_min_trades"):
            if k in ex:
                kw[k] = ex[k]
        return cls(**kw)

    @property
    def accum_window_s(self) -> float:
        """Absorption accumulation window: the FIRST phase after the shock (buys/new-wallets counted here)."""
        return self.absorption_window_slots * SLOT_SECONDS

    @property
    def eval_window_s(self) -> float:
        """Fire instant = absorption + stabilization: the machine evaluates only after the second phase."""
        return (self.absorption_window_slots + self.stabilization_window_slots) * SLOT_SECONDS

    @property
    def stabilization_window_s(self) -> float:
        return self.stabilization_window_slots * SLOT_SECONDS


@dataclass
class _MintDetectorV2(_MintDetector):
    r_trough: float = field(default=float("inf"))   # Rmin: lowest external SOL after the shock

    def on_line(self, line: dict) -> dict | None:
        ts = float(line["ts"])
        trader = line.get("trader")
        side = line.get("side")
        sol = float(line.get("sol_amount") or 0.0)

        self.cluster.observe(line)
        r_now = ecr.real_quote_sol(line)
        cov_now = ecr.coverage_ratio(line, self.cfg.q_sol)
        self.recent.append((ts, r_now, cov_now, line))

        if self.state == "WATCH":
            if self._try_arm(line, ts, trader, side, sol):
                self.r_trough = r_now          # trough starts at the POST-dump R (R0 - S), not R0
            if trader:
                self.seen_wallets.add(trader)
            return None

        # state == ARMED --------------------------------------------------------------------------
        # Absorption ACCUMULATION happens only in the first phase (<= t_shock + accum_window_s), against
        # the cluster frozen at ARM. The trough Rmin tracks the whole ARMED span.
        if r_now < self.r_trough:
            self.r_trough = r_now

        if ts <= self.t_shock + self.cfg.accum_window_s:
            if side == "buy" and trader is not None and trader not in self.armed_cluster and sol > 0:
                self.absorb_buy_sol += sol
                if trader not in self.seen_wallets:
                    self.absorb_new_wallets.add(trader)
            if trader:
                self.seen_wallets.add(trader)
            return None

        # still inside the STABILIZATION phase (accum end .. eval end): observe, don't fire yet.
        if ts <= self.t_shock + self.cfg.eval_window_s:
            if trader:
                self.seen_wallets.add(trader)
            return None

        # eval window closed -> evaluate once, disarm, let this same line re-arm a fresh shock.
        decision = self._evaluate(line)
        self._disarm_v2()
        if self._try_arm(line, ts, trader, side, sol):
            self.r_trough = r_now          # post-dump R of the fresh shock
        if trader:
            self.seen_wallets.add(trader)
        return decision

    def flush(self, now_ts: float) -> dict | None:
        """Force-close an ARMED position whose FULL eval window (absorption + stabilization) has elapsed."""
        if self.state == "ARMED" and now_ts > self.t_shock + self.cfg.eval_window_s:
            last_line = self.recent[-1][3] if self.recent else {"mint": None, "ts": now_ts}
            decision = self._evaluate(last_line)
            self._disarm_v2()
            return decision
        return None

    def _disarm_v2(self) -> None:
        self._disarm()
        self.r_trough = float("inf")

    def _tail(self, now_ts: float):
        """Bound the tail's UPPER edge at `now` (the absorption end super()._evaluate passes). V1's _tail
        has no upper bound because V1 fires AT accumulation end (nothing later sits in `recent`); V2 fires
        after the stabilization phase, so without this the capacity/coverage tail would leak later
        stabilization-window samples into the absorption-end check. (review: confirmed defect)"""
        return [(t, r, c) for (t, r, c, _l) in self.recent if now_ts - self.cfg.tail_s <= t <= now_ts]

    def _flow_is_sell_dominated(self, fire_ts: float) -> dict:
        """Non-cluster flow over the veto window ending at the fire instant — the entry-flow-veto signal
        (identical shape to the resolver's FLOW_FLIP so 'no exit condition already true' is exact)."""
        win = self.cfg.flow_window_slots * SLOT_SECONDS
        sells = tot = 0.0
        n = 0
        for (t, _r, _c, ln) in self.recent:
            if t < fire_ts - win or t > fire_ts:
                continue
            trader = ln.get("trader")
            s = float(ln.get("sol_amount") or 0.0)
            if trader is None or trader in self.armed_cluster or s <= 0:
                continue
            tot += s
            n += 1
            if ln.get("side") == "sell":
                sells += s
        frac = (sells / tot) if tot > 0 else 0.0
        dominated = (tot >= self.cfg.flow_min_window_sol and n >= self.cfg.flow_min_trades
                     and frac >= self.cfg.flow_flip_sell_frac)
        return {"sell_frac": round(frac, 4), "window_sol": round(tot, 4), "trades": n, "dominated": dominated}

    def _stabilization_ok(self) -> dict:
        """Final stabilization sub-window: external R non-declining (net reserve flow >= 0) and no cluster
        wallet resumed materially selling within it."""
        if not self.cfg.stabilization_requires_positive_net_reserve_flow:
            return {"ok": True, "checked": False}
        start = self.t_shock + self.cfg.accum_window_s
        sub = [(t, r, ln) for (t, r, _c, ln) in self.recent if t >= start]
        if not sub:
            return {"ok": False, "reason": "no stabilization samples"}
        r_first = sub[0][1]
        r_last = sub[-1][1]
        non_declining = r_last >= r_first - 1e-12
        cluster_resumed = any(
            ln.get("side") == "sell" and ln.get("trader") in self.armed_cluster
            and float(ln.get("sol_amount") or 0.0) >= self.cfg.material_sell_frac_of_R * max(1e-12, self.r_pre)
            for (_t, _r, ln) in sub)
        ok = non_declining and not cluster_resumed
        return {"ok": ok, "checked": True, "r_first": round(r_first, 4), "r_last": round(r_last, 4),
                "cluster_resumed": cluster_resumed}

    def _evaluate(self, line: dict) -> dict:
        dec = super()._evaluate(line)   # V1 gates: absorb, capacity(@recover_frac=1.0), concentration, coverage
        v1_fired = not dec["control"]

        Rt = float(dec["r_at_fire"] or 0.0)
        S = float(dec["sell_sol"] or 0.0)
        R0 = float(dec["r_pre"] or 0.0)
        Rmin = self.r_trough if self.r_trough != float("inf") else Rt
        nrr = ((Rt - Rmin) / S) if S > 0 else 0.0
        nrr_ok = nrr >= self.cfg.net_replacement_ratio_min

        # Entry-veto. Base (all arms): coverage already at/above the exit buffer is guaranteed by the entry
        # floor, and an immediately-unsellable curve can't pass coverage either; the meaningful veto is the
        # STRICT flow-veto (arms B/C): don't buy into a tape already flipping to sells.
        flow = self._flow_is_sell_dominated(float(line["ts"]))
        veto_hit = bool(self.cfg.veto_strict and flow["dominated"])
        veto_ok = not veto_hit

        stab = self._stabilization_ok()

        fired = v1_fired and nrr_ok and veto_ok and stab["ok"]
        dec["control"] = not fired
        dec["nrr"] = round(nrr, 4)
        dec["r_min"] = round(Rmin, 6)
        dec["conditions"]["net_replacement"] = {
            "ok": nrr_ok, "nrr": round(nrr, 4), "min": self.cfg.net_replacement_ratio_min,
            "R0": round(R0, 4), "Rmin": round(Rmin, 4), "Rt": round(Rt, 4), "S": round(S, 4)}
        dec["conditions"]["entry_veto"] = {"ok": veto_ok, "strict": self.cfg.veto_strict, "flow": flow}
        dec["conditions"]["stabilization"] = stab
        return dec


class DetectorV2(Detector):
    """Fan-out V2 detector. One instance per ARM (arms differ by veto_strict; the exit differs in resolve)."""

    def __init__(self, cfg: DetectorV2Config) -> None:
        self.cfg = cfg
        self._mints: dict = {}

    def on_line(self, line: dict):
        mint = line.get("mint")
        if mint is None:
            return None
        d = self._mints.get(mint)
        if d is None:
            d = self._mints[mint] = _MintDetectorV2(cfg=self.cfg)
        return d.on_line(line)


def detector_for_arm(spec: dict, arm: dict) -> DetectorV2:
    """Build the V2 detector for one frozen arm ({'arm','veto_strict',...})."""
    cfg = DetectorV2Config.from_spec(spec, veto_strict=bool(arm.get("veto_strict")))
    return DetectorV2(cfg)
