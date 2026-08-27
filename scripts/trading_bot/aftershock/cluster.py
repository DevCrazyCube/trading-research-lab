#!/usr/bin/env python3
"""Per-mint cluster tracker for AFTERSHOCK — token-weighted, slot-windowed. PAPER, deterministic.

Mirrors the sniper rugrisk substrate (deployer proxy = first observed buyer; per-wallet accumulation)
but token-weighted and windowed over the first `cluster_window_slots` from the mint's first trade:

  * DEPLOYER proxy       = the first BUY wallet seen for the mint (rugrisk pattern).
  * CLUSTER set C(mint)  = deployer ∪ the top-`early_buyer_top_k` wallets by cumulative tokens BOUGHT
                           within the cluster window [t0, t0 + window]. This is the "dangerous inventory"
                           whose sell AFTERSHOCK waits to see absorbed.
  * k60                  = max_w (tokens bought by w) / Σ_w (tokens bought by w) over the window — the
                           B20B concentration proxy (largest early buyer's share). k60 >= 0.95 == the
                           lone-bag-holder / no-external-money regime B20B rejects.
  * per-wallet HOLDINGS  = cumulative bought − sold tokens (for the "top non-reserve holder not rising"
                           concentration check during the absorption window).

Deterministic: same tape order -> same state. No network, no RNG. Feeds `detector.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ClusterState:
    """Accumulated per-mint cluster/holdings state, updated tape-line by tape-line in time order."""
    t0: float | None = None
    deployer: str | None = None
    window_s: float = 24.0                          # cluster_window_slots × SLOT_SECONDS
    early_top_k: int = 3
    bought_in_window: dict = field(default_factory=dict)   # wallet -> tokens bought within [t0, t0+window]
    holdings: dict = field(default_factory=dict)           # wallet -> cumulative bought - sold (all time)
    _frozen_cluster: frozenset | None = None               # C(mint), frozen at window close

    def observe(self, line: dict) -> None:
        """Fold one tape line (ts, trader, side, token_amount) into the state."""
        ts = float(line["ts"])
        trader = line.get("trader")
        side = line.get("side")
        tok = float(line.get("token_amount") or 0.0)
        if self.t0 is None:
            self.t0 = ts
        if trader is None or tok <= 0:
            return
        # deployer proxy = first BUY wallet
        if self.deployer is None and side == "buy":
            self.deployer = trader
        # running holdings (all time)
        signed = tok if side == "buy" else -tok
        self.holdings[trader] = self.holdings.get(trader, 0.0) + signed
        # cumulative BOUGHT within the cluster window (only buys, only inside the window)
        if side == "buy" and self.t0 is not None and ts <= self.t0 + self.window_s:
            self.bought_in_window[trader] = self.bought_in_window.get(trader, 0.0) + tok

    def k60(self) -> float | None:
        """Largest early buyer's share of all tokens bought in the window (B20B concentration proxy)."""
        total = sum(self.bought_in_window.values())
        if total <= 0:
            return None
        return max(self.bought_in_window.values()) / total

    def cluster(self, ts: float | None = None) -> frozenset:
        """C(mint) = deployer ∪ top-k early buyers by tokens bought in the window. Frozen once the window
        has closed (ts past t0+window) so ARMED/absorption logic sees a stable cluster; before then it is
        computed live from what has been seen so far."""
        window_closed = (self.t0 is not None and ts is not None and ts > self.t0 + self.window_s)
        if window_closed and self._frozen_cluster is not None:
            return self._frozen_cluster
        top = sorted(self.bought_in_window.items(), key=lambda kv: kv[1], reverse=True)
        members = {w for w, _ in top[: self.early_top_k]}
        if self.deployer:
            members.add(self.deployer)
        c = frozenset(members)
        if window_closed:
            self._frozen_cluster = c
        return c

    def top_nonreserve_holder_frac(self) -> float | None:
        """Top-1 wallet's share of positive holdings (a crude concentration read for the 'not rising'
        check). Reserve/PDA vaults are not user wallets on the tape, so positive holdings ~= user float."""
        pos = [h for h in self.holdings.values() if h > 0]
        total = sum(pos)
        if total <= 0:
            return None
        return max(pos) / total
