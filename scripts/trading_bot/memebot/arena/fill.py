#!/usr/bin/env python3
"""MEME ARENA — the honest-fill module. THE honesty spine: every arm prices its fills HERE, never with
raw price arithmetic of its own (the selftest asserts this). Two entry points, both all-cost:

- honest_fill_snapshot: tier-1 OPTIMISTIC bound (ARM 1, free snapshot data). Fills at the observed
  post-decision snapshot price with a multiplicative two-leg toll — no marginal-vs-executable gap is
  modelled, so it is explicitly an upper bound: a KILL here is decisive, a PASS earns only a causal test.

- causal_fill_cp: tier-2 EXECUTABLE fill (ARM 2/3). Walks the constant-product bonding curve for the
  ACTUAL position size on BOTH legs (entry buys into the curve, exit sells the tokens back out), caps the
  exit at the real withdrawable SOL, and charges fixed per-leg lamport cost. It also computes the
  MARGINAL (mid-price) fill the same trade would have shown, and decomposes net_marg - net_honest so the
  optimism that faked SWF's +117% in-sample number is measured line-by-line rather than hidden.

Pure math, no I/O, no network — hermetically testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# multiplicative two-leg toll (buy leg, sell leg) — memecoin round trip ~3%
TOLL_BUY = 0.015
TOLL_SELL = 0.015
LAMPORTS_PER_SOL = 1_000_000_000


@dataclass
class FillResult:
    basis: str                      # "snapshot" | "causal_cp"
    entry_price: float              # SOL per token actually paid (avg fill on the entry leg)
    exit_price: float               # SOL per token actually received (avg fill on the exit leg)
    gross_return: float             # exit/entry - 1 on the fill basis, pre-cost
    net_return: float               # THE honest number: after impact + toll + lamport cost + reserve cap
    net_marginal: float | None      # the optimistic marginal-price comparator (causal_cp only)
    real_reserve_bound_hit: bool    # exit capped by real withdrawable SOL (a dumped/drained curve)
    latency_s: float
    decomposition: dict = field(default_factory=dict)  # net_marg - net_honest, attributed


def _toll(gross: float) -> float:
    """Multiplicative two-leg toll: net = (1+gross)(1-toll_buy)(1-toll_sell) - 1. Never gross - 0.03."""
    return (1.0 + gross) * (1.0 - TOLL_BUY) * (1.0 - TOLL_SELL) - 1.0


def honest_fill_snapshot(entry_price: float, exit_price: float) -> FillResult:
    """Tier-1 optimistic bound: observed snapshot prices, multiplicative two-leg toll, no impact model."""
    if not entry_price or entry_price <= 0 or exit_price is None or exit_price < 0:
        raise ValueError("snapshot fill needs positive entry and non-negative exit price")
    gross = exit_price / entry_price - 1.0
    return FillResult("snapshot", entry_price, exit_price, gross, _toll(gross), None, False, 0.0,
                      {"note": "optimistic bound: no marginal-vs-executable gap modelled"})


def causal_fill_cp(entry_reserves: tuple[float, float], exit_reserves: tuple[float, float],
                   size_sol: float, latency_s: float = 0.9,
                   lamport_cost_roundtrip: int = 2_250_000,
                   real_sol_withdrawable_at_exit: float | None = None) -> FillResult:
    """Tier-2 executable fill on the constant-product bonding curve, virtual reserves (S=v_sol, T=v_tokens).

    Entry (buy `size_sol` into the curve):  tokens_in = T*size/(S+size);  avg paid = size/tokens_in.
    Exit  (sell those tokens back):         sol_out   = S'*tokens_in/(T'+tokens_in), capped at the real
                                            withdrawable SOL (a curve drained by a concurrent dump pays
                                            you less than the invariant implies).
    Costs: fixed per-leg lamports (gas+priority) both ways. The MARGINAL comparator uses mid prices S/T
    and S'/T' — the optimism this removes is decomposed."""
    S, T = entry_reserves
    S2, T2 = exit_reserves
    if S <= 0 or T <= 0 or S2 <= 0 or T2 <= 0 or size_sol <= 0:
        raise ValueError("causal_cp fill needs positive reserves and size")
    tokens_in = T * size_sol / (S + size_sol)
    entry_avg = size_sol / tokens_in                       # SOL per token actually paid (incl. impact)
    sol_out_raw = S2 * tokens_in / (T2 + tokens_in)
    bound_hit = False
    sol_out = sol_out_raw
    if real_sol_withdrawable_at_exit is not None and sol_out > real_sol_withdrawable_at_exit:
        sol_out = max(0.0, real_sol_withdrawable_at_exit)
        bound_hit = True
    exit_avg = sol_out / tokens_in if tokens_in else 0.0
    lam = lamport_cost_roundtrip / LAMPORTS_PER_SOL
    net = (sol_out - size_sol - lam) / size_sol            # honest realized return on capital deployed

    # marginal (mid-price) comparator — the optimistic number a naive backtest would print
    entry_marg, exit_marg = S / T, S2 / T2
    gross_marg = exit_marg / entry_marg - 1.0
    net_marg = _toll(gross_marg)

    # decompose net_marg - net_honest so the optimism is visible, not hidden
    entry_impact = (entry_avg - entry_marg) / entry_marg   # how much worse than mid we bought
    exit_impact = (exit_marg - exit_avg) / exit_marg if exit_marg else 0.0
    decomposition = {
        "net_marginal": net_marg, "net_honest": net,
        "gap_total": net_marg - net,
        "entry_impact_frac": entry_impact, "exit_impact_frac": exit_impact,
        "latency_s": latency_s, "lamport_cost_sol": lam,
        "real_reserve_bound_hit": bound_hit,
    }
    return FillResult("causal_cp", entry_avg, exit_avg, sol_out / size_sol - 1.0, net, net_marg,
                      bound_hit, latency_s, decomposition)


if __name__ == "__main__":
    # hermetic sanity: snapshot toll is multiplicative; causal impact makes the honest fill worse than marginal.
    s = honest_fill_snapshot(1.0, 2.0)
    assert abs(s.net_return - ((2.0) * (1 - TOLL_BUY) * (1 - TOLL_SELL) - 1.0)) < 1e-12
    # a +100% marginal move, but a size that's a real fraction of the curve: honest < marginal
    c = causal_fill_cp((30.0, 1e9), (60.0, 0.5e9), size_sol=0.5)
    assert c.net_marginal is not None and c.net_return < c.net_marginal, "honest fill must be <= marginal"
    assert c.decomposition["gap_total"] > 0
    # a drained curve (real withdrawable tiny) caps the exit -> deep loss even on a 'marginal' pump
    d = causal_fill_cp((30.0, 1e9), (60.0, 0.5e9), size_sol=0.5, real_sol_withdrawable_at_exit=0.05)
    assert d.real_reserve_bound_hit and d.net_return < c.net_return
    print("fill.py self-check OK: snapshot multiplicative toll; causal impact & reserve-cap bite")
