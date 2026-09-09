# Pre-registration: creator self-buy size filter (Grok's second mechanism) on the v3 tape

Frozen 2026-09-09 by Claude before any return in this design was computed. Paper only, NO_TRADE.
Provenance: the gen-1 panel's single positive cell (dev-buy share >= 20%: +4.6% mean net, 12 winners of 172, "unstratified,
untested elsewhere" per the 2026-09-08 audit). This is its first out-of-sample test on survivorship-free data.

## Data
v3 tape (10,122 successful CreateEvents; 1.16M trades with wallet, SOL amount, reserves; CompleteEvents). Population = every
in-window launch. Creator = CreateEvent.creator (and `user` if different).

## Signal (fixed)
SELF = total SOL of the creator's buys with slot <= create_slot + 2 (the create transaction and the next two slots, ~0.8 s).
Thresholds T in {0.2, 1, 5} SOL. Signal slot = the last qualifying creator buy's slot. Also reported as bins for the
graduation-lift check (0 / (0,0.2) / [0.2,1) / [1,5) / >=5 SOL), organic graduation = CompleteEvent > 5 min after create.

## Entry, exits, costs (fixed)
Entry = first trade with slot >= signal_slot + L, L in {5, 32, 450} slots (~2 s, ~13 s = our measured feed lag, ~3 min =
Grok's cadence), filled on that trade's post-state; 0.05 SOL; exact constant-product fill; recorded fee bps (1.25%/side);
105,000 lamports per transaction. If the curve completed before the entry trade, the launch is NOT ENTERABLE and is
reported as such (it cannot be traded on the curve; post-migration is outside the tape).
Exits: +15 min, +60 min, end-of-tape (last curve state before completion), plus the frozen handling rule H4 (trailing 0.85
of peak once >= 1.5x) as a secondary. Unexitable positions charged -30/-50/-100% with resolution rate.

## Placebo
Shuffled sizes: each launch is assigned another launch's SELF value (chronological shuffle within the same split); the
identical pipeline is run. The rule must beat its own shuffled version by more than the CI half-width.

## Split, metrics, pass
Chronological 60/40 by create slot. Mint-equal mean AND median, win rate, entered/not-enterable counts, 95% CI clustered by
creator and by 30-min session (wider wins). Primary cell (single holdout read): T = 1 SOL, L = 32 slots, exit +60 min.
PASS = holdout mean > 0 with CI-low > 0 after Bonferroni over 27 cells (3T x 3L x 3 exits), median > 0, and beats the
shuffled placebo. Prediction, written first: graduation lift by self-buy size is real and large; the enterable subset's
net return is negative at L >= 32 slots because the self-buy is visible to 0-second bots and priced before we act;
L = 5 slots may be positive for T = 5 SOL, which retail cannot execute.
