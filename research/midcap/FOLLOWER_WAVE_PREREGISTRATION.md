# Pre-registration: follower wave after a broadcast leader's fill (Grok round-4 Q2)

Frozen 2026-09-09 by Claude before any event is recorded by this instrument. Paper only, NO_TRADE.

## Hypothesis (counterparty = followers, trigger = leader; the signal's author is not the counterparty)
FOMO leaderboard traders have followers who receive a push ~15 s after the leader's on-chain fill and act manually
30 s–minutes later (Grok, unverified). If that wave exists and is material, a position taken at the leader's fill + L
(websocket latency) and sold into the wave is a retail-latency trade against human-speed flow.

## Roster
The frozen 30/30 roster (Codex, 2026-09-09 15:20 UTC). Board = leaders with followers; control = random active wallets.

## Instrument
`scripts/trading_bot/memebot/follower_wave_watch.py`: websocket logsSubscribe(mentions=wallet, commitment=confirmed) on all
60 wallets; on each notification the transaction is fetched and per-owner deltas decoded; a BUY (tokens in, USDC or SOL out)
is an EVENT with fill time = blockTime and avail_ns = local receipt after decode. At +20 min the mint's largest pool's last
300 trades (GeckoTerminal, includes tx_from_address, kind, volume) and minute bars are fetched and stored raw.

## Measurement (fixed)
Per event: distinct buyers and buy volume (USD) in windows (-15,0], (0,1], (1,5], (5,15] min around the fill (the leader's
own trade excluded). WAVE RATIO = distinct new buyers in (0,5] / distinct buyers in (-15,0] (0 -> +1 smoothing). Mint-equal
median and mean of the ratio per arm; 95% CI by wallet cluster. WAVE EXISTS if the board median ratio > control median ratio
by more than the CI half-width AND board median absolute new buyers in (0,5] >= 5.
Only if WAVE EXISTS, the candidate rule is read (single read): paper entry at the OPEN of the first minute bar strictly after
avail_ns; exits at +3 min, +5 min, and the first minute after +2 min where buy volume < sell volume; toll 1.14% AMM /
2.48% curve; dropouts -30/-50/-100. PASS = board mean > 0 with CI-low > 0 AND median > 0 AND beats control, >= 25 events.
Prediction, written first: the wave exists for the top-followed leaders but is small (median new buyers < 5 in 5 min);
the rule is not positive after toll because the leader's own fill already moved the price.
