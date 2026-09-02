# The pump.fun bonding curve, measured (2026-09-02)

Run on `research/b11a/` — 3,932 survivorship-free curves from a single 23h launch window, 333,888 exact
reserve observations, 11.9 days of follow. Every number below was computed this session.

## Three structural facts (new, and none of them were known here before)

**1. The curve is hard-floored at the launch price.**
**0 of 3,239** priced curves ever traded below their first observed price. Worst drawdown-from-first-price
across the entire cohort: **0.000%**. This is curve math, not luck: virtual SOL starts at 30 and cannot go
below it, and the AMM's liquidity is always present on-curve. **On-curve, downside is set entirely by your
entry premium above the floor — not by the coin "going to zero."**

**2. Graduation pays a deterministic prize.**
All 82 graduates show an identical **+1369.4%** on-curve run, because completion is a fixed point of the
curve: 30 → 115 virtual SOL under constant product is exactly **14.69x**. The prize is not a distribution;
it is a constant.

**3. The unconditional graduation base rate is 2.085%** (82 / 3,932).

## The tempting (and false) conclusion

Those three facts give EV = (1 + 13.69·p)/m − 1 − toll, where m = entry ÷ floor. At the unconditional
p = 2.085% that breaks even at **m = 1.248** and pays **+25.5%** at the floor — and entry premium *falls*
with delay (median m = 1.138 at 0s, 1.015 at 60s, 1.000 at 300s), implying "be patient, not fast."

**This is wrong, and it is wrong in exactly the way everything else here has been wrong: p was assumed,
not measured, conditional on the entry.**

## The conditional measurement that kills it

Graduation rate conditioned on momentum at t+60s:

| entry m at t+60s | n | graduates | graduation rate |
|---|---|---|---|
| 1.00–1.05 | 2284 | 3 | **0.13%** |
| 1.05–1.25 | 541 | 2 | 0.37% |
| 1.25–2.0 | 162 | 2 | 1.23% |
| 2.0–5.0 | 167 | 15 | 8.98% |
| >5.0 | 85 | 60 | **70.59%** |

Momentum predicts graduation with a **540x lift** — a genuinely large, real signal. But the cheap entries
are cheap *because they are dead*: the 2.085% "base rate" is a blend of 0.13% dead coins and 70% runners.

## Exact per-coin simulation (no assumed entry, no assumed base rate)

Enter at the observed price at t+T, exit at the last on-curve price (graduation price for graduates),
net of a 3% round trip:

| entry m | n | mean net | median | win% | t |
|---|---|---|---|---|---|
| **t+60s** | | | | | |
| 1.00–1.05 | 1256 | −1.9% | −4.7% | 0.5% | −1.00 |
| 1.05–1.25 | 541 | −7.1% | −9.6% | 1.1% | −2.34 |
| 1.25–2.0 | 162 | −23.7% | −34.4% | 3.1% | −2.82 |
| 2.0–5.0 | 167 | −28.7% | −67.9% | 9.6% | −2.82 |
| >5.0 | 40 | −14.2% | −85.1% | 37.5% | −0.88 |
| **t+300s** | | | | | |
| 1.00–1.05 | 928 | **+2.1%** | −3.2% | 0.6% | **+0.71** |
| >5.0 | 46 | −47.1% | −85.4% | 23.9% | −4.16 |

**Every entry premium is ≤ 0.** The best cell is buying at the floor after 5 minutes: +2.1% at t = +0.71 —
statistically zero, and before impact and latency.

## What this actually establishes

The bonding curve is **efficiently priced in the one dimension we can see**. Momentum genuinely predicts
graduation, and the price fully impounds it: by the time a coin reveals itself as a likely graduate, you
pay enough that the 14.69x is gone. That is a *measured efficiency result*, not a failure to look.

**Therefore any remaining edge must be orthogonal to the price path** — a signal that predicts graduation
better than the first 60 seconds of price already does. Price-derived rules are closed. The untested axis
is **provenance**: creator wallet history, funder wallet, bundled supply in the create tx, sniper share of
the first-N-slot buyers. We hold that data (`b11a_bodies.sqlite`: 326k decoded bodies, `instruction.accounts_json`
→ buyer wallets) and have never used it, and the labels (82 graduations) are already on disk.

**Next decisive test:** does any provenance feature lift graduation probability *above what price at t+60s
already implies*? That is a clean, cheap, well-posed classification question with the holdout
(`research/b11m_window2/`) still sealed.
