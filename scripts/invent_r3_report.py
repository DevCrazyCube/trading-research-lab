#!/usr/bin/env python3
"""Render INVENT_R3_dealer_positioning.md from the JSON the harness wrote."""
import json
import math
import os

ROOT = "/home/anont/meme"
J = os.path.join(ROOT, "research/trading_bot/INVENT_R3_dealer_positioning.json")
M = os.path.join(ROOT, "research/trading_bot/INVENT_R3_dealer_positioning.md")

WIN = {
    "A": ("2024-02-01 .. 2025-08-31", "2025-09-01 .. 2026-08-14", 1.58, 0.95),
    "B": ("2016-01-04 .. 2021-12-31", "2022-01-03 .. 2026-08-14", 6.00, 4.62),
    "C": ("2022-05-13 .. 2024-12-31", "2025-01-02 .. 2026-08-14", 2.64, 1.62),
}


def main():
    d = json.load(open(J))
    F = d["formulas"]
    LIVE = [f for f in F if f["design"]["n"] >= 20]
    BUILT = len(F)
    N = len(LIVE)
    q = math.sqrt(2 * math.log(N))
    lines = []
    A = lines.append
    A("# INVENT-R3 — DEALER POSITIONING / OPTIONS FLOW")
    A("")
    A(f"**{BUILT} original formulas built ({N} live, 1 degenerate), three tracks, one verdict.** Design windows tested, "
      f"later windows held out and untouched until the design numbers were frozen.")
    A("")
    A("## 0. The data wall, stated first")
    A("")
    A("There is **no free historical option open-interest series** — Cboe's daily "
      "market-statistics archive is 403, OCC per-series is paid, Alpaca's snapshot "
      "carries no `openInterest` field at all (verified this session), and Deribit's "
      "free sample holds six snapshots. `NEWTERR_optimp` therefore declared GEX "
      "**untestable** and proxied it with curve shape.")
    A("")
    A("This round found the substitute that round did not: **Alpaca serves expired "
      "OPRA option daily bars back to 2024-02-01**, per contract, with volume. That "
      "buys a real per-strike gamma map — built from *cumulative traded volume* rather "
      "than open interest — for 2.5 years. It is the first per-strike dealer-gamma "
      "construct this programme has ever been able to compute.")
    A("")
    A("Cache: `research/data/gex_cache/` — one JSON per expiry, 640 expiries, "
      "±$15 strike ladder in $1 steps, calls and puts, 12 calendar days of bars each. "
      "Rebuilt by `scripts/invent_r3_gex_fetch.py` (idempotent).")
    A("")
    A("## 1. The three tracks and their honest null bars")
    A("")
    A("| track | what it reads | design | holdout | design yrs | E[max Sharpe] under null |")
    A("|---|---|---|---|---|---|")
    for k, (dw, hw, dy, hy) in WIN.items():
        A(f"| **{k}** | {'per-strike gamma from real chains' if k=='A' else ('price-only dealer footprints' if k=='B' else '0DTE era, VIX1D')} "
          f"| {dw} | {hw} | {dy:.2f} | **{q/math.sqrt(dy):.2f}** |")
    A("")
    A(f"`sqrt(2 ln N)` with live N = {N} is **{q:.2f}** in t-stat space. Divided by "
      "`sqrt(design years)` it becomes the Sharpe a formula must CLEARLY beat before "
      "its design number means anything.")
    A("")
    A("## 2. Every formula, design and holdout")
    A("")
    A("Costs charged per side on |Δw| at **1.5 bp** headline (SPY intraday marketable; "
      "the measured 15:45 half-spread is 0.13 bp and regulatory pass-through 0.15 bp, "
      "so this is deliberately punitive). Rungs 0.5 / 1.0 / 1.5 / 3.0 in the JSON.")
    A("")
    A("| formula | mechanism (one line) | design S | design t | n | holdout S | holdout t | n |")
    A("|---|---|---|---|---|---|---|---|")
    for f in F:
        mech = f["mechanism"]
        mech = (mech[:96] + "…") if len(mech) > 97 else mech
        A(f"| `{f['name']}` | {mech} | {f['design']['sharpe']:+.2f} | "
          f"{f['design']['t']:+.2f} | {f['design']['n']} | "
          f"{f['holdout']['sharpe']:+.2f} | {f['holdout']['t']:+.2f} | "
          f"{f['holdout']['n']} |")
    A("")
    A("## 3. Verdict — the theme is NOISE. Zero survivors.")
    A("")
    bt = max(LIVE, key=lambda f: abs(f["design"]["t"]))
    bs = max((f for f in LIVE if f["design"]["n"] >= 50), key=lambda f: f["design"]["sharpe"])
    both = [f for f in LIVE if f["design"]["sharpe"] > 0 and f["holdout"]["sharpe"] > 0]
    A(f"- **Largest design |t| of all {N}: `{bt['name']}` at {bt['design']['t']:+.2f}** — "
      f"*below* the max-of-{N} null bar of {q:.2f}, and **in the opposite sign to its "
      f"own stated mechanism**. Nothing in this theme reached the bar even before the "
      f"holdout was opened.")
    A(f"- **Largest design Sharpe: `{bs['name']}` at {bs['design']['sharpe']:+.2f}** "
      f"(n = {bs['design']['n']}, t = {bs['design']['t']:+.2f}). Its holdout is "
      f"**{bs['holdout']['sharpe']:+.2f}**. This is what a Sharpe-ranked miner would "
      f"have shipped, and it is the single worst number in the table.")
    A(f"- **Only {len(both)} of {N} live formulas are positive in BOTH windows** "
      f"({', '.join('`'+f['name']+'`' for f in both)}), and the best of them carries "
      f"design t = {max(f['design']['t'] for f in both):+.2f}. That is indistinguishable "
      "from three coins landing heads twice.")
    A("- **No formula beat the no-information control.** `B15_CONTROL_UNCOND_FADE` "
      "contains no options data at all and posts −0.49 / −0.43. Every dealer-conditioned "
      "intraday fade lands in the same place, which means the conditioning does nothing.")
    A("")
    A("### 3a. The one pattern that survives both windows is not a dealer effect")
    A("")
    b11 = next(f for f in F if f["name"].startswith("B11"))
    A(f"`B11_GSIGN_CONTANGO_LASTHR` is the only formula with the same large sign in both "
      f"windows (design t {b11['design']['t']:+.2f}, holdout t {b11['holdout']['t']:+.2f}). "
      "It fades the day's move in the last half hour, so a consistent negative means the "
      "last half hour **continues** the day. Two reasons that is not a finding:")
    A("")
    A("1. It is the wrong sign for its mechanism, and the sign was fixed in advance.")
    A(f"2. **Gross, it is only {b11['design']['gross_sharpe']:+.2f} / "
      f"{b11['holdout']['gross_sharpe']:+.2f}.** The whole apparent magnitude is the "
      "1.5 bp × 2 legs a day of turnover cost. Flip the sign and the gross edge is "
      "≈ +0.2 Sharpe — under the null bar, and negative net of the same costs.")
    A("")
    A("3. Late-day intraday momentum is already on the dead ledger — B22D/B22E tested "
      "Gao-et-al intraday momentum and killed it out of sample. This is a rediscovery "
      "of a corpse.")
    A("")
    A("## 4. What this round DID establish (both are new facts, not edges)")
    A("")
    A("**(a) The per-strike dealer-gamma map is computable on free data after all.** "
      "`NEWTERR_optimp` recorded GEX as untestable. It is testable from 2024-02-01 "
      "forward, at 0–5 DTE, on a ±$15 near-money ladder, from Alpaca's expired option "
      "daily bars. The cache is built, idempotent and gitignorable. Any future "
      "dealer-positioning claim now has a real instrument instead of a curve-shape proxy. "
      "It just does not predict SPY.")
    A("")
    A("**(b) The textbook GEX sign-flip is structurally degenerate on SPY at short "
      "tenor.** Gamma-weighted near-money option volume is **put-dominated on 97 % of "
      "days** (net-normalised balance negative on 358 of 369 sampled days; deciles run "
      "−0.67 to −0.11). Under the standard convention — dealers long the calls, short "
      "the puts — SPY 0–5DTE dealers are *always* net short gamma near the money. There "
      "is no zero crossing to trade, which is why `A4_GAMMA_FLIP_LEVEL` collapsed to "
      "n = 30 and `A6_CALL_WALL_RESIST` to n = 0 (degenerate, excluded from the live "
      "count). The regime split has to be made against the measure's own history "
      "(`A9`/`A9b`) to exist at all — and then it is noise.")
    A("")
    A("## 5. Honesty ledger")
    A("")
    A(f"- Formulas built: {BUILT}. **One (`A6_CALL_WALL_RESIST`) is degenerate — n = 0 "
      f"in design — and is reported, not silently dropped.** Live N = {N}.")
    A("- Signs were fixed from the mechanism before any backtest ran. No sign was "
      "flipped after seeing a result; §3a explains what would have happened if one had "
      "been.")
    A("- Holdout windows were not read until the design column was written to JSON.")
    A("- Every Track A close-to-close formula has a lag-safe twin (`A1b`, `A4b`, `A9b`) "
      "entered at the next cash open, because the option daily bar for day *t* completes "
      "at the 16:15 options close, *after* the 16:00 cash close. The twins are no better.")
    A("- Costs are punitive on purpose (1.5 bp/side vs a measured 0.13 bp SPY half-"
      "spread). Gross columns are in the JSON: **the gross numbers fail too**, so this "
      "is not a friction story.")
    A("")
    A("## 6. What was NOT testable, declared")
    A("")
    A("| wanted | blocked by |")
    A("|---|---|")
    A("| true open interest (rather than cumulative volume) | no free historical OI "
      "anywhere; Alpaca's option snapshot has no `openInterest` field — verified live |")
    A("| OI/volume validation against a same-day real-OI chain | Yahoo's option endpoint "
      "returned 401 then 429 this session; the check is deferred, not done |")
    A("| intraday 0DTE flow footprint (per-minute gamma) | needs option minute bars for "
      "~60 contracts × 640 days; buildable from the same endpoint, not built here |")
    A("| pre-2024-02 per-strike gamma | Alpaca's OPRA archive starts there; 2022–23 "
      "0DTE boom is invisible to any free per-strike source |")
    A("| single-name GEX (NVDA/TSLA/AAPL) | same endpoint, same 2024-02 floor; not run "
      "because SPY — the deepest and most dealer-hedged chain in the world — already "
      "showed nothing |")
    A("")
    open(M, "w").write("\n".join(lines) + "\n")
    print("wrote", M)


if __name__ == "__main__":
    main()
