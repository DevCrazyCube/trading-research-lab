#!/usr/bin/env python3
"""AFTERSHOCK detector — the per-mint WATCH -> ARMED -> ABSORPTION state machine over the trade tape.

The whole strategy in one object. It NEVER pre-buys. It watches a mint from birth; when a cluster
wallet fires the first MATERIAL sell (the rug-like shock), it opens an absorption test window and only
FIRES an entry if external, non-cluster demand demonstrably absorbs the shock AND exit capacity holds
AND concentration is falling AND the exact position-sized coverage stays above a frozen floor. A shock
that is NOT absorbed becomes a CONTROL observation (same machinery, scored identically) — that is the
honest null: "the rug fired but nobody caught it."

Deterministic replay: feed tape lines in time order via `on_line`; it returns a fire dict (PASS or
CONTROL) at the instant the absorption window closes, else None. Slot thresholds are wall-clock via
SLOT_SECONDS (the tape is not slot-stamped — see the build spec GAP-2).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from . import ecr
from .cluster import ClusterState

SLOT_SECONDS = 0.4


@dataclass(frozen=True)
class DetectorConfig:
    q_sol: float = 0.1
    cluster_window_slots: int = 60
    early_buyer_top_k: int = 3
    material_sell_sol_floor: float = 0.5
    material_sell_frac_of_R: float = 0.25
    absorption_window_slots: int = 60
    absorb_mult: float = 1.0
    absorb_min_new_wallets: int = 3
    capacity_recover_frac: float = 0.90
    capacity_tail_slots: int = 10
    k60_max: float = 0.95
    coverage_entry_floor: float = 10.0

    @classmethod
    def from_spec(cls, det: dict) -> "DetectorConfig":
        return cls(**{k: det[k] for k in det if k in cls.__dataclass_fields__})

    @property
    def cluster_window_s(self) -> float:
        return self.cluster_window_slots * SLOT_SECONDS

    @property
    def absorb_window_s(self) -> float:
        return self.absorption_window_slots * SLOT_SECONDS

    @property
    def tail_s(self) -> float:
        return self.capacity_tail_slots * SLOT_SECONDS


@dataclass
class _MintDetector:
    cfg: DetectorConfig
    cluster: ClusterState = None                        # type: ignore
    state: str = "WATCH"
    seen_wallets: set = field(default_factory=set)      # wallets seen at any time (for 'new wallet')
    recent: deque = field(default_factory=lambda: deque(maxlen=4000))  # (ts, R, coverage, line)
    # ARMED context:
    t_shock: float = 0.0
    sell_sol: float = 0.0
    r_pre: float = 0.0
    top_frac_at_shock: float | None = None
    absorb_buy_sol: float = 0.0
    absorb_new_wallets: set = field(default_factory=set)
    armed_cluster: frozenset = field(default_factory=frozenset)   # C frozen at ARM (review #1)

    def __post_init__(self):
        if self.cluster is None:
            self.cluster = ClusterState(window_s=self.cfg.cluster_window_s,
                                        early_top_k=self.cfg.early_buyer_top_k)

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
            self._try_arm(line, ts, trader, side, sol)
            if trader:
                self.seen_wallets.add(trader)
            return None

        # state == ARMED
        # accumulate absorption within (t_shock, t_shock+W] against the cluster FROZEN at ARM (review #1:
        # a live cluster lets a big absorber climb into top-k and be wrongly excluded from absorption).
        if ts <= self.t_shock + self.cfg.absorb_window_s:
            if side == "buy" and trader is not None and trader not in self.armed_cluster and sol > 0:
                self.absorb_buy_sol += sol
                if trader not in self.seen_wallets:
                    self.absorb_new_wallets.add(trader)
            if trader:
                self.seen_wallets.add(trader)
            return None

        # window closed -> EVALUATE all conditions ONCE, disarm, then let this same line re-arm a fresh
        # shock (review #15: the window-closing line is otherwise never tested for being a material sell).
        decision = self._evaluate(line)
        self._disarm()
        self._try_arm(line, ts, trader, side, sol)
        if trader:
            self.seen_wallets.add(trader)
        return decision

    def _try_arm(self, line: dict, ts: float, trader, side, sol: float) -> bool:
        """Arm on a MATERIAL cluster sell; snapshot the cluster at the shock instant. Returns armed?."""
        if side != "sell" or trader is None or sol <= 0:
            return False
        c = self.cluster.cluster(ts)
        r_before = self._r_before(ts)
        if not (trader in c and sol >= self.cfg.material_sell_sol_floor
                and r_before > 0 and sol >= self.cfg.material_sell_frac_of_R * r_before):
            return False
        self.state = "ARMED"
        self.t_shock = ts
        self.sell_sol = sol
        self.r_pre = r_before
        self.top_frac_at_shock = self.cluster.top_nonreserve_holder_frac()
        self.absorb_buy_sol = 0.0
        self.absorb_new_wallets = set()
        self.armed_cluster = c   # freeze C at the shock (dangerous inventory), disjoint from later absorbers
        return True

    def flush(self, now_ts: float) -> dict | None:
        """Force-close an ARMED position whose absorption window has objectively elapsed in WALL-CLOCK
        time even though the tape went silent (review #2: else a dead/rugged mint stays ARMED forever and
        the honest-null CONTROL is never recorded -> survivorship bias toward absorbed shocks)."""
        if self.state == "ARMED" and now_ts > self.t_shock + self.cfg.absorb_window_s:
            last_line = self.recent[-1][3] if self.recent else {"mint": None, "ts": now_ts}
            decision = self._evaluate(last_line)
            self._disarm()
            return decision
        return None

    def _r_before(self, ts: float) -> float:
        """R(t) STRICTLY before the current line. If no earlier sample exists, 0.0 — never the current
        (post-event) line's R (review #14), which would corrupt the material-sell R ratio."""
        for (t, r, _c, _l) in reversed(self.recent):
            if t < ts:
                return r
        return 0.0

    def _tail(self, now_ts: float):
        """Samples within the last tail_s before now_ts."""
        return [(t, r, c) for (t, r, c, _l) in self.recent if t >= now_ts - self.cfg.tail_s]

    def _evaluate(self, line: dict) -> dict:
        now = self.t_shock + self.cfg.absorb_window_s
        tail = self._tail(now)
        reasons = {}

        # (c) ABSORB: external non-cluster buy SOL >= absorb_mult × sell_sol AND >= min new wallets.
        absorb = (self.absorb_buy_sol >= self.cfg.absorb_mult * self.sell_sol
                  and len(self.absorb_new_wallets) >= self.cfg.absorb_min_new_wallets)
        reasons["absorb"] = {"ok": absorb, "buy_sol": round(self.absorb_buy_sol, 4),
                             "need_sol": round(self.cfg.absorb_mult * self.sell_sol, 4),
                             "new_wallets": len(self.absorb_new_wallets)}

        # (b) CAPACITY HELD: R(t) >= capacity_recover_frac × R_pre across the tail.
        cap_ok = bool(tail) and all(r >= self.cfg.capacity_recover_frac * self.r_pre for (_t, r, _c) in tail)
        reasons["capacity_held"] = {"ok": cap_ok, "r_pre": round(self.r_pre, 4),
                                    "tail_min_R": round(min((r for _t, r, _c in tail), default=0.0), 4)}

        # (d) CONCENTRATION: k60 < k60_max AND top-1 holder share not rising vs the shock instant.
        k60 = self.cluster.k60()
        top_now = self.cluster.top_nonreserve_holder_frac()
        conc_ok = (k60 is not None and k60 < self.cfg.k60_max
                   and (self.top_frac_at_shock is None or top_now is None
                        or top_now <= self.top_frac_at_shock + 1e-9))
        reasons["concentration"] = {"ok": conc_ok, "k60": (round(k60, 4) if k60 is not None else None),
                                    "top_frac_shock": self.top_frac_at_shock,
                                    "top_frac_now": (round(top_now, 4) if top_now is not None else None)}

        # (e) COVERAGE FLOOR: coverage >= floor across the tail AND non-decreasing slope (last-first >= 0).
        covs = [c for (_t, _r, c) in tail]
        cov_ok = bool(covs) and all(c >= self.cfg.coverage_entry_floor for c in covs) and (covs[-1] - covs[0] >= -1e-9)
        reasons["coverage_floor"] = {"ok": cov_ok, "floor": self.cfg.coverage_entry_floor,
                                     "tail_min_cov": round(min(covs), 3) if covs else None}

        fired = absorb and cap_ok and conc_ok and cov_ok
        return {
            "control": not fired,                 # PASS if all pass; CONTROL (null) if the shock was not absorbed
            "mint": line.get("mint"),
            "t_shock": self.t_shock,
            "sell_sol": self.sell_sol,
            "r_pre": self.r_pre,
            "r_at_fire": ecr.real_quote_sol(line),
            "coverage_at_fire": ecr.coverage_ratio(line, self.cfg.q_sol),
            "cluster_wallets": sorted(self.cluster.cluster(line["ts"])),
            "deployer": self.cluster.deployer,
            "k60_at_fire": self.cluster.k60(),
            "entry_line": line,                   # the tape line at the fire instant (reserves frozen here)
            "conditions": reasons,
        }

    def _disarm(self) -> None:
        self.state = "WATCH"
        self.absorb_buy_sol = 0.0
        self.absorb_new_wallets = set()


class Detector:
    """Fan-out detector across many mints. `on_line` routes a tape line to its mint's state machine."""

    def __init__(self, cfg: DetectorConfig | None = None) -> None:
        self.cfg = cfg or DetectorConfig()
        self._mints: dict[str, _MintDetector] = {}

    def on_line(self, line: dict) -> dict | None:
        mint = line.get("mint")
        if mint is None:
            return None
        d = self._mints.get(mint)
        if d is None:
            d = self._mints[mint] = _MintDetector(cfg=self.cfg)
        return d.on_line(line)

    def flush(self, now_ts: float) -> list:
        """Force-close every ARMED mint whose absorption window has elapsed in wall-clock time. Returns
        the list of decisions (each a CONTROL or, rarely, a PASS the closing tape simply never arrived for)."""
        out = []
        for d in self._mints.values():
            dec = d.flush(now_ts)
            if dec is not None:
                out.append(dec)
        return out

    def drop(self, mint: str) -> None:
        self._mints.pop(mint, None)

    def tracked(self) -> int:
        return len(self._mints)
