# B22C — broker execution quality: the measurement contradicts the consensus

**Why this matters more than it sounds.** Schwarz et al. found a **6.5× spread** in round-trip cost
across brokers on identical, simultaneous orders. At the per-trade edges available to us, that single
choice is plausibly larger than any signal refinement we could build.

**Status.** External literature. Nothing measured by us.

---

## 1. The measurement, and how it was made

Schwarz, Barber, Huang, Jorion & Odean, *The "Actual Retail Price" of Equity Trades*,
**Journal of Finance 80(5), 2025, 2507–2541**. Six accounts at five brokers, **85,000 simultaneous
market orders** — the same trade, at the same instant, at every broker, so differences cannot be
explained by timing or stock selection.

| broker | price improvement (% of spread) |
|---|---|
| TD Ameritrade | **47%** — best |
| Fidelity | ~35% |
| E*TRADE | ~35% |
| Robinhood | 27% |
| **Interactive Brokers (Pro)** | **19% — worst** |

**Mean account-level round-trip cost: 0.07% to 0.46%, excluding commissions.**

*Reported secondhand from the abstract and summaries; the full text is paywalled (Wiley 402, SSRN
403). The per-broker ordering should be re-verified against the published table before acting.*

## 2. Why IBKR ranks last, and why that is not the same as "IBKR is bad"

The naive reading — "avoid IBKR" — is wrong, and the reason is structural. Dyhrberg, Shkilko &
Werner, *The Retail Execution Quality Landscape*, **Journal of Financial Economics 168 (2025)**,
using all US equities in Rule 605 data, Jan 2019 – Mar 2022:

| | wholesalers (PFOF) | exchanges |
|---|---|---|
| **share of marketable orders price-improved (S&P 500)** | **75%** | **12%** |
| effective spread | 49.06 bps | 46.98 bps |
| price impact | 32.53 bps | 47.32 bps |
| realized spread (what the intermediary keeps) | +16.53 bps | −0.34 bps |
| NBBO width when they execute | 64.92 bps | 48.67 bps |

A typical retail order in an S&P 500 stock receives **price improvement of 44% of the quoted spread**,
and wholesaler intermediation saves retail investors **close to $1bn per month** in aggregate.

**The reconciliation.** IBKR **Pro** routes to exchanges and its own ATS, and does *not* take PFOF.
IBKR **Lite** routes to wholesalers and does. Exchanges price-improve **12%** of marketable orders;
wholesalers price-improve **75%**. So IBKR Pro's last-place finish on *price improvement* is a direct
consequence of its routing model, not incompetence — and it comes with a commission on top.

**Therefore the right broker depends entirely on whether you take or make liquidity:**

| how you trade | what you want |
|---|---|
| **market / stop orders** (pure liquidity taking) | a **wholesaler-routing** broker. You are buying price improvement, and exchanges barely offer it. |
| **resting limit orders** (providing liquidity) | **IBKR Pro** or similar. You collect rather than pay the spread, and routing control plus rebates matter more than price improvement you will never receive. |

**This inverts the folk wisdom for our case.** Every broker-comparison site I searched names IBKR
"best for execution." Those are affiliate-funded. The academic measurement says that for a *market
order*, IBKR Pro was the worst of five. **The ORB strategy enters with stop orders — market orders by
another name — so under ORB you would be a taker on every single entry**, which is precisely the
regime where IBKR Pro measured worst.

Note the opposite conclusion for [B22D](B22D_INTRADAY_MOMENTUM_CANDIDATE.md), whose exit is a
market-on-close order filled in the closing auction at a single clearing price — no spread, and
routing is irrelevant.

## 3. Two things that make the ranking stale

**TD Ameritrade no longer exists as a separate broker.** Schwab completed the acquisition and client
migration. The study's best performer cannot be opened today, and whether its routing survived the
migration into Schwab is not established by anything found here. **Do not act on the TDA row.**

**Rule 605 changes on 1 August 2026.** The SEC's amendments — originally due 14 Dec 2025, extended to
**1 Aug 2026** — require **large retail brokers to file Rule 605 reports for the first time**, broken
down by order size, with effective spread, price improvement, execution speed, fill rates, and a new
effective-over-quoted-spread (EFQ) measure.

> Until now, brokers were not required to publish this. From August 2026 they are. **The comparison
> Schwarz et al. had to run 85,000 live orders to make becomes a public filing.** That is the single
> highest-value thing to check once the first reports land, and it is free.

## 4. What to do

1. **Do not switch brokers on this yet.** The ranking predates the Schwab/TDA merger and the Rule 605
   regime change, and its per-broker detail is secondhand here.
2. **Match the broker to the order type**, per the table in §2 — that logic is structural and does not
   go stale.
3. **Check the first Rule 605 filings after 1 Aug 2026.** They settle the question with public data.
4. **Prefer strategies whose costs are structurally small** over strategies that need a good broker to
   survive. B22D's exit is free by market design; that is worth more than any broker choice.

---

*Sources: Schwarz, Barber, Huang, Jorion & Odean, J. Finance 80(5) 2025 (per-broker figures
secondhand, paywalled); Dyhrberg, Shkilko & Werner, JFE 168 (2025), read in full from the working
paper; SEC Rule 605 amendments and the Oct 2025 compliance-date extension.*
