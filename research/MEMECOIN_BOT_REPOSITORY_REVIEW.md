# Public Memecoin Bot Repository Review

Reviewed: 2026-07-27. Snapshot time: approximately 09:30–09:51 UTC.

## Executive conclusion

The publicly marketed repository landscape returned by this search is overwhelmingly composed of transaction executors, copy bots, configurable snipers, volume tools, Telegram front ends, advertisements, and repackaged code. It contains useful execution components, but almost no visible public evidence of a complete research loop connecting point-in-time data, leakage-safe labels, realistic simulation, calibrated selection, live reconciliation, and statistically credible net performance. This does not imply that private, unmarketed, deleted, or differently named systems lack such capabilities.

The central industry mistake is therefore not one universally bad entry signal. It is confusing the ability to submit a buy and sell transaction with possession of a trading edge.

This review inspected 61 public repositories returned by a GitHub search for `pump.fun trading bot`, exceeding the requested minimum of 50. Every selected repository was shallow-cloned without running its code. Findings describe the visible snapshot, not private branches, hosted products, deleted history, or maintainers' unobservable live results.

## Method and limitations

### Discovery

- Queried GitHub's public repository search API for `pump.fun trading bot`, ordered by stars.
- The query reported 216 candidates at review time.
- Inspected the first 100 search results and selected 60 bot-like candidates spanning snipers, copy traders, monitoring tools, ML claims, arbitrage, migration bots, and volume bots.
- Added the separately identified Chainstack Pump.fun/Bonk.fun bot, producing 61 reviewed repositories.

This is a broad reproducible search, not a mathematically exhaustive census. GitHub search ranking, SEO spam, deleted/private repositories, alternate terminology, and API indexing create coverage bias.

### Static evaluation

For each snapshot, this review checked:

- Presence and amount of inspectable source.
- Strategy type and whether selection logic exists.
- Historical recorder, persistent data model, and point-in-time state.
- Backtest, paper, dry-run, or simulator support.
- Fees, slippage, latency, failed transactions, and exit modeling.
- Rug, creator, holder, wallet, or funding-cluster analysis.
- Tests, CI, dependency locks, and operational controls.
- Pump/PumpSwap compatibility evidence and protocol-version awareness.
- Security smells such as committed `.env` files or opaque archives.
- Exact and obvious near-duplicate repository families.

Repository-owned test files were detected with a static path/name heuristic after excluding committed `node_modules`; this measures visible test artifacts, not coverage or quality. Exact duplicates were identified by equality of Git `HEAD^{tree}` hashes. Near-clone families were assigned conservatively through manual comparison of directory structure, filenames, implementation organization, documentation, and packaged assets; no numeric similarity threshold was used, so their count is qualitative.

No untrusted code, install script, binary, archive, dependency, or trading transaction was executed. A keyword match was not accepted as proof that a feature worked. README claims are explicitly treated as claims unless supported by visible code or tests.

### Meaning of “went wrong”

Public repositories rarely disclose verified PnL, fill logs, or failure postmortems. This report does **not** claim that maintainers lost money. “Failure” means a visible gap that prevents the repository from establishing or preserving a defensible trading edge.

## Aggregate findings

| Finding | Observed count | Interpretation |
|---|---:|---|
| Repositories inspected | 61 | Requested minimum exceeded. |
| Repository-owned test files detected by static naming heuristic | 7 | Visible test artifacts are uncommon; this is not a coverage measurement. |
| Repositories with GitHub Actions workflows | 5 | Build/test reproducibility is uncommon. |
| No conventional `.rs`, `.ts`, `.js`, `.py`, `.go`, `.java`, or `.cs` source detected | 11 | Many results are advertisements, screenshots, archives, or README-only shells. |
| Tracked root `.env` file | 5 | Unsafe secret-handling example even when current values are placeholders. Contents were not reproduced. |
| Exact full-tree duplicate pairs | 2 pairs | `henrytirla`/`bodyAce15` and `TobiCrackIT`/`LEOSOLAR8`. |
| Additional obvious near-clone families | At least 4 | Rebranding inflates apparent ecosystem diversity. |

Counts are conservative static observations from the reviewed commits. Test-like files inside committed `node_modules` were excluded. Separately, the structured review found no repository displaying public evidence across the complete checklist of immutable point-in-time observations, explicit anti-leakage feature construction, exact execution-aware simulation, chronological walk-forward evaluation, calibrated selection, and reconciled net results. That is a qualitative absence-of-evidence finding, not a mechanically counted proof of nonexistence.

## Repository-by-repository evaluation

Maturity labels describe usefulness for our objective:

- **Component:** meaningful reusable engineering, but not proof of a profitable strategy.
- **Prototype:** inspectable bot code with major research or operational gaps.
- **Fragment:** narrow example or incomplete implementation.
- **Shell:** README, screenshots, opaque archive, or negligible inspectable implementation.
- **Misaligned:** primarily generates/artificially manages volume rather than finding an honest trading edge.

| # | Repository | Type | Visible strengths | Principal gap for a defensible edge | Lesson for us |
|---:|---|---|---|---|---|
| 1 | [chainstacklabs/pumpfun-bonkfun-bot](https://github.com/chainstacklabs/pumpfun-bonkfun-bot) | Component | Large inspectable Python implementation; multiple listeners; official IDLs; Geyser; priority fees; TP/SL; CI; unusually current 2026 Pump account-layout notes. | README roadmap says token analysis was not started; learning examples are not a research-grade simulator; no visible wallet graph, labels, walk-forward evaluation, or net-performance evidence. | Reuse decoder/execution ideas, not its strategy assumptions. Pin upstream IDL revisions and add our research/data layer. |
| 2 | [WSOL12/Solana-Arbitrage-Bot](https://github.com/WSOL12/Solana-Arbitrage-Bot) | Fragment | Simple TypeScript arbitrage entry point and configuration. | One source file, no tests/CI, no visible market-state reconstruction, fill competition, inventory risk, or profitability study. | Multi-venue claims require atomicity, quote freshness, failed-leg modeling, and measured net capture. |
| 3 | [coffellas-cto/Solana-Copy-Trading-Bot](https://github.com/coffellas-cto/Solana-Copy-Trading-Bot) | Prototype | Rust source, streaming/Jito-oriented execution, configurable copy flow. | No tests or evidence that copied wallets remain profitable after detection lag, price impact, tips, and crowding. | Copy decisions need point-in-time leader selection and follower-specific executable attribution. |
| 4 | [henrytirla/Solana-Trading-Bot](https://github.com/henrytirla/Solana-Trading-Bot) | Component examples | Multiple Python buy/sell/Jito/wrapped-SOL examples. | Exact duplicate of repository #42; examples are execution recipes, not a strategy, simulator, or risk system; protocol freshness is uncertain. | Treat as reference code only and verify every account layout against current official IDLs. |
| 5 | [TreeCityWes/Pump-Fun-Trading-Bot-Solana](https://github.com/TreeCityWes/Pump-Fun-Trading-Bot-Solana) | Fragment | Minimal JavaScript buy/sell automation. | Four files, no tests, persistence, selection intelligence, simulator, or current-regime evidence. | Minimal transaction submission is not a bot architecture. |
| 6 | [hanshaze/solana-sniper-copy-mev-trading-bot](https://github.com/hanshaze/solana-sniper-copy-mev-trading-bot) | Shell | Broad discussion of tools and approaches. | No conventional source detected; asset/README-heavy SEO surface; performance and feature claims cannot be audited. | Reject unauditable “profitable/MEV/AI” claims at intake. |
| 7 | [bigmacman1129/solana-sniper-trading-mev-bot](https://github.com/bigmacman1129/solana-sniper-trading-mev-bot) | Prototype | Inspectable TypeScript, several transaction executors, listeners, filters, TP/SL and slippage configuration. | No tests/CI or visible leakage-safe research; safety filters and stops are not demonstrated against cluster-controlled holders or liquidity races. | Separate execution adapters from scientifically validated selection and exit-hazard models. |
| 8 | [bitman09/pumpfun-sniper-bot](https://github.com/bitman09/pumpfun-sniper-bot) | Prototype | Substantial TypeScript and packaged Pump SDK; SOL/USDC-oriented description; execution controls. | Vendored package reduces auditability; no tests/CI, historical simulator, wallet graph, or performance evidence. | Prefer source-pinned official SDK/IDL inputs and independently validate USDC/fee regimes. |
| 9 | [FLOCK4H/Dexter](https://github.com/FLOCK4H/Dexter) | Component | Most research-oriented competitor: PostgreSQL, creator leaderboard, raw events, paper/simulate/live modes, backtest command, risk profiles, three tests. | Core hypothesis largely copies historically ranked creators; visible evidence does not establish leakage-safe ranking, cluster independence, realistic slot-order fills, or statistically valid performance. | Study its operational/data ergonomics, but use point-in-time creator features inside broader hazard/return models. |
| 10 | [imcrazysteven/SOL-TRADING-BOT](https://github.com/imcrazysteven/SOL-TRADING-BOT) | Prototype | Large Telegram trading interface with DEX integrations. | User-facing execution product, not autonomous edge research; no owned tests/CI or defensible selection model. | Keep user interface out of the critical path until data and simulation are proven. |
| 11 | [justFiveDev/Solana-Copy-Trading-Bot](https://github.com/justFiveDev/Solana-Copy-Trading-Bot) | Prototype | Compact Rust copy engine with Jito/streaming claims. | No tests, persistence, source-wallet performance model, adverse-selection analysis, or follower fill study. | A copied sale will usually be detected after the leader; model asymmetric lag explicitly. |
| 12 | [imcrazysteven/Solana-Copy-Trading-Bot](https://github.com/imcrazysteven/Solana-Copy-Trading-Bot) | Prototype | Inspectable TypeScript Pump/Jupiter utilities and basic state. | No tests/CI and no method for selecting wallets without survivorship bias or measuring follower net PnL. | Store every candidate wallet and rank it only using history available then. |
| 13 | [bigmacman1129/solana-copy-trading-bot](https://github.com/bigmacman1129/solana-copy-trading-bot) | Prototype | Modular JS streaming, executor, storage, price checking, logging, and notification. | No tests/CI; JSON position storage; broad DEX claims without protocol-version tests; no copied-wallet decay/crowding research. | Require durable event-sourced state and per-venue compatibility fixtures. |
| 14 | [imcrazysteven/Pumpfun-Volume-Bot](https://github.com/imcrazysteven/Pumpfun-Volume-Bot) | Misaligned | Inspectable multi-wallet/transaction automation. | Goal is volume generation, not predictive trading; may manufacture precisely the activity our models must discount and raises market-abuse concerns. | Use only as adversarial-pattern research; never implement artificial volume. |
| 15 | [mooncitydev/solana-copytrading-bot](https://github.com/mooncitydev/solana-copytrading-bot) | Prototype | Rust, Pump/Raydium copy flow, Jito and WebSocket orientation. | No tests, lockfile, research recorder, wallet-selection methodology, or executable performance evidence. | Language speed does not solve information lag or selection bias. |
| 16 | [ahk780/solana-copy-trading-bot](https://github.com/ahk780/solana-copy-trading-bot) | Prototype | Modular JS executor/storage/price components. | Near-clone family with #13; no tests/CI and no empirical edge validation. | Detect upstream clones before treating stars/repos as independent evidence. |
| 17 | [crash-predictor1/solana-pumpfunx-sniper-bot](https://github.com/crash-predictor1/solana-pumpfunx-sniper-bot) | Prototype | Rust source, build tooling, one test-like file, configurable execution/risk language. | Keyword-heavy positioning; no complete data/simulator/model evidence and no CI. | Score evidence in code and experiments, never marketing density. |
| 18 | [TobiCrackIT/tg-solana-tradingbot](https://github.com/TobiCrackIT/tg-solana-tradingbot) | Prototype | Substantial Telegram trading implementation. | Exact duplicate of #51; no tests/CI and no autonomous strategy research. | Deduplicate code lineage in competitor studies and training corpora. |
| 19 | [whisdev/rust-copy-trading](https://github.com/whisdev/rust-copy-trading) | Component | Largest Rust codebase in this sample; includes Barter engine, test files, dependabot/CI, and data-oriented terms. | Complexity is not accompanied by public Pump-specific point-in-time wallet selection, executable simulation, or performance attribution; vendored/embedded framework increases audit surface. | Modular engines are useful only after narrowing and validating the Pump-specific decision problem. |
| 20 | [greengod63/pump-fun-bot](https://github.com/greengod63/pump-fun-bot) | Component | Substantial Python, raw transaction fixtures, listener tests, learning examples, PumpSwap examples. | Its roadmap explicitly leaves token analysis and Geyser unstarted and describes TP/SL status informally; not a complete strategy/research system. | Raw fixtures and decoder tests are worth emulating; build intelligence separately. |
| 21 | [alphaoinker/Pumpswap-Volume-Bot](https://github.com/alphaoinker/Pumpswap-Volume-Bot) | Misaligned shell | Describes multi-wallet PumpSwap volume generation. | README only; no auditable source; artificial-volume objective is not a legitimate selection edge. | Model these patterns as adversarial flow and exclude the behavior from our system. |
| 22 | [Trustdev-eth/solana-trading-bot-service](https://github.com/Trustdev-eth/solana-trading-bot-service) | Shell | Catalogues bot-service capabilities. | README only; no inspectable implementation or verifiable claims. | Services and source-code advertisements are leads, not evidence. |
| 23 | [micanny/solsniper](https://github.com/micanny/solsniper) | Prototype | TypeScript, Docker, blacklist/configuration, multi-source scanner framing. | No tests/CI and no realistic execution simulator; API scanning can lag and omit on-chain state. | Source new pools directly on-chain and quantify provider delay/dropout. |
| 24 | [adams322111233221/pump-fun-swap-raydium-trading-bot](https://github.com/adams322111233221/pump-fun-swap-raydium-trading-bot) | Component | Good Rust separation for Pump, Raydium, pools, transactions, API, Jito examples; CI present. | Execution library rather than demonstrated strategy; no owned tests detected, recorder, wallet risk, or net performance study. | Potential reference for venue adapters; surround with fixtures and exact state reconciliation. |
| 25 | [dwlee91/solana-pumpfun-sniper-bot](https://github.com/dwlee91/solana-pumpfun-sniper-bot) | Fragment | Small sniping implementation. | Minimal source; tracks a root `.env`; no tests, research, persistence, or current Pump regime evidence. | Never track `.env`; add precommit secret detection and use a remote signer. |
| 26 | [Trustdev-eth/raydium-pumpfun-copy-trading-bot-v2](https://github.com/Trustdev-eth/raydium-pumpfun-copy-trading-bot-v2) | Prototype | Geyser utility and Pump/Raydium transaction handling. | No tests/CI; “next block” copy premise ignores queue position, price impact, leader sale asymmetry, and wallet selection decay. | Record observed-to-land latency distributions and simulate follower placement, not ideal next-block fills. |
| 27 | [slightlyuseless/pumpfun-terminal](https://github.com/slightlyuseless/pumpfun-terminal) | Component UI | Inspectable self-hosted wallet/trading terminal and state/log modules. | Manual/terminal workflow rather than predictive system; uses third-party PumpPortal; no tests or research-quality simulation. | A control terminal may be useful later, but should consume—not define—the core research engine. |
| 28 | [lincolnlewin8/Solona-Simple-Pumpfun-Sniper](https://github.com/lincolnlewin8/Solona-Simple-Pumpfun-Sniper) | Fragment | Minimal JavaScript sniper. | No conventional source extension detected beyond package/`sniper.mjs` categorization; tracks `.env`; no tests or evidence. | Secret hygiene and basic validation precede live use. |
| 29 | [Cloud-Dev77/Telegram_Solana_Pump.fun_Sniping_bot](https://github.com/Cloud-Dev77/Telegram_Solana_Pump.fun_Sniping_bot) | Fragment | Migration monitoring concept with Telegram/Bitquery integration. | One source file; API dependency; no tests, fill model, wallet intelligence, or post-migration fee/version study. | Migration is a regime transition, not automatically an entry signal. |
| 30 | [rasmiin/pumpfunGoBot](https://github.com/rasmiin/pumpfunGoBot) | Shell | Configuration and packaged desktop artifact. | Source is an opaque ZIP; implementation and security cannot be audited. | Do not inspect or run opaque bot archives with keys. |
| 31 | [hoziertom44-arch/solana_pumpswap_migration_bot](https://github.com/hoziertom44-arch/solana_pumpswap_migration_bot) | Fragment | Clear, narrow Python migration strategy and configuration/display separation. | Few files, no tests/CI, third-party dependencies, no evidence that migration entry survives post-graduation sell pressure and fee discontinuity. | Explicitly model pre/post-migration mechanics and inventory selling before using graduation as confirmation. |
| 32 | [yllvar/gmgn-sniping](https://github.com/yllvar/gmgn-sniping) | Prototype | Working-looking GMGN API integration and deployment material. | Commits `node_modules` and a root `.env`; apparent test count came from dependencies, not owned tests; third-party API determines visibility/execution. | Never vendor runtime dependencies or secrets; archive raw provider responses and maintain an independent on-chain truth path. |
| 33 | [smartdev00/Sniper-Bot](https://github.com/smartdev00/Sniper-Bot) | Prototype | Inspectable TypeScript monitoring and trade code. | No tests/CI, recorder, realistic simulator, clustered risk, or measured edge. | New-token detection is commodity infrastructure, not selection alpha. |
| 34 | [ChangeYourself0613/Telegram-Trading-Bot](https://github.com/ChangeYourself0613/Telegram-Trading-Bot) | Prototype | Large Telegram multi-DEX implementation. | Obvious near-clone family with #10/#18/#51; no owned tests and no strategy validation. | Repackaged execution UIs should count once when assessing innovation. |
| 35 | [PumpFunTradingBot/JS-DEX-Solana-PumpFun-Trading-Bot-V5-PumpFunTradingBot](https://github.com/PumpFunTradingBot/JS-DEX-Solana-PumpFun-Trading-Bot-V5-PumpFunTradingBot) | Shell | Screenshots and packaged artifact. | Only one visible JS file plus ZIP/images; profitability language is unsupported; auditability is poor. | Exclude opaque promotional bundles from the trusted supply chain. |
| 36 | [A5-/pumpfun-pumpswap-sniper-bot](https://github.com/A5-/pumpfun-pumpswap-sniper-bot) | Prototype | Rust implementation, Pump/PumpSwap focus, three test-like files and captured logs. | No CI, recorder/model evaluation, wallet clustering, or evidence the tests cover current protocol versions and economic correctness. | Convert captured transactions into versioned golden fixtures and add economic invariants. |
| 37 | [Code-Quang/pumpfun-raydium-sniper-jito-bundle-bot](https://github.com/Code-Quang/pumpfun-raydium-sniper-jito-bundle-bot) | Prototype | Rust, Yellowstone/Jito-oriented design, Pump/Raydium scope. | No tests/CI, historical dataset, selection model, or net fill evidence. | Fast transport must be benchmarked end-to-end and attached to a selective policy. |
| 38 | [SOLCodeWriter/SOLCodeWriter-Solana-PumpFun-Trading-JS-DEX-Bot-V5](https://github.com/SOLCodeWriter/SOLCodeWriter-Solana-PumpFun-Trading-JS-DEX-Bot-V5) | Shell | Packaged artifact and UI screenshots. | Near-clone of #35/#48; negligible inspectable code and unsupported profit language. | Repository count is not independent technical evidence. |
| 39 | [0xffffa/trader.fun](https://github.com/0xffffa/trader.fun) | Prototype | Interesting Go implementation with bonding-curve code and an ONNX indicator. | No disclosed training dataset, label, feature timing, calibration, simulator, tests, or model-card evidence; opaque model artifact cannot establish edge. | Version data/model lineage and reproduce every model from point-in-time inputs. |
| 40 | [wicky-rx/pumpfun_tradingbot](https://github.com/wicky-rx/pumpfun_tradingbot) | Shell | Describes Pump/Raydium price tracking. | README only; no auditable implementation. | Claims without source or experimental artifacts receive zero evidentiary weight. |
| 41 | [chootradingbot/solana-raydium-pump-fun-bot](https://github.com/chootradingbot/solana-raydium-pump-fun-bot) | Shell | Screenshots of Telegram product. | No conventional source; white-label service advertisement. | Hosted product claims cannot seed our architecture without measurable API/transaction evidence. |
| 42 | [bodyAce15/Solana-TradingBot-Python](https://github.com/bodyAce15/Solana-TradingBot-Python) | Component examples | Same useful Python execution examples as #4. | Exact tree duplicate of #4; no independent innovation or performance evidence. | Use tree hashes and similarity checks in ecosystem research. |
| 43 | [kthenurseone/pumpfun_volumebot](https://github.com/kthenurseone/pumpfun_volumebot) | Misaligned shell | Describes wallet/volume automation. | README only and artificial-volume objective. | Treat as potential wash-pattern documentation, not a strategy template. |
| 44 | [apuente93/solana-trading-bot](https://github.com/apuente93/solana-trading-bot) | Fragment | Very small scanner/trader and CSV logging. | One source file; no tests; CSV is not a complete recorder; filters/backtest terms lack realistic execution evidence. | First build immutable raw events and canonical state, then strategy code. |
| 45 | [ahk780/pumpfun-copy-trading-bot](https://github.com/ahk780/pumpfun-copy-trading-bot) | Component UI | Substantial React interface and server for configuring copied wallets. | UI dominates; only one test-like file, no CI, no source-wallet selection research, crowding model, or executable attribution. | A polished dashboard can conceal an unvalidated decision rule; research metrics must lead product work. |
| 46 | [MSB0095/sol_beast](https://github.com/MSB0095/sol_beast) | Component | Strong Rust execution architecture, on-chain IDLs, Helius sender, priority fee/tip handling, dry mode, TP/SL/timeout, docs and CI. | No repository-owned tests detected despite README test instructions; heuristics are configurable rather than empirically justified; no historical recorder, wallet graph, or execution-faithful evaluation. | Strong candidate for studying sender/risk implementation. Replace generic filters with calibrated models and live reconciliation. |
| 47 | [7finger0x/trading-bot](https://github.com/7finger0x/trading-bot) | Shell | Docker/requirements framing and broad scanner/rug-source description; CI file. | No conventional implementation source detected; external-service/Telegram dependency; claims cannot be audited. | CI existence alone does not imply a functioning or tested bot. |
| 48 | [SolanaPumpFunBot/SolanaPumpFunBot-Solana-PumpFun-Trading-DEX-JS-Bot-V5](https://github.com/SolanaPumpFunBot/SolanaPumpFunBot-Solana-PumpFun-Trading-DEX-JS-Bot-V5) | Shell | Packaged artifact and screenshots. | Same obvious promotional family as #35/#38; minimal visible code. | Do not download or run binary/archive-centric competitors with trading keys. |
| 49 | [nemez428/pump-fun-pump-swap-sniper-copy-bot](https://github.com/nemez428/pump-fun-pump-swap-sniper-copy-bot) | Prototype | Rust Pump/PumpSwap copy/sniper code and build tooling. | Near-family with #17/#36; no tests/CI, research recorder, wallet selection proof, or performance evidence. | Code lineage and current-program compatibility require direct verification. |
| 50 | [pumpfun-trader/pumpfun-trading-bot](https://github.com/pumpfun-trader/pumpfun-trading-bot) | Prototype | Scanner, copy flow, logging, holder/liquidity/rug scoring documentation and two test-like scripts. | Documentation claims 99% rug-detection accuracy without visible benchmark methodology; thresholds appear hand-configured; no leakage-safe dataset, calibration, wallet clustering, or executable simulator. | Never publish accuracy without class balance, temporal split, label definition, confidence intervals, and reproducible predictions. |
| 51 | [DevSolanaB/PumpFun-Bump-BOT](https://github.com/DevSolanaB/PumpFun-Bump-BOT) | Misaligned fragment | Small JavaScript buy/sell cycling automation. | Bump/volume behavior is not predictive trading; only two source files and no tests. | Keep market-manipulation behavior outside the product and use it only to design detection features. |
| 52 | [LEOSOLAR8/Telegram-Solana-Tradingbot](https://github.com/LEOSOLAR8/Telegram-Solana-Tradingbot) | Prototype | Substantial Telegram execution code. | Exact tree duplicate of #18; no independent strategy or evidence. | Deduplicate before drawing ecosystem-level conclusions. |
| 53 | [staindev/pumpswap-copy-trading-bot-rust](https://github.com/staindev/pumpswap-copy-trading-bot-rust) | Prototype | Rust PumpSwap IDL and copy-target flow. | Tracks `.env`; no tests/CI, wallet-selection evaluation, or realistic follower simulation. | Enforce secret scanning and measure copy delay/adverse selection per target. |
| 54 | [maninder772/Pumptools-bot](https://github.com/maninder772/Pumptools-bot) | Shell | Cross-chain auto-snipe/anti-rug product description. | README/license only; no auditable implementation or evidence. | “Anti-rug” is a claim until labels and temporal evaluation are published. |
| 55 | [rio-15/Real-Time-Pump.fun-Token-Monitoring-System](https://github.com/rio-15/Real-Time-Pump.fun-Token-Monitoring-System) | Component decoder | Useful transaction decoder/event parser and bonding helper with Pump IDL. | Monitoring only, old snapshot, no execution, tests, canonical state, commitment reconciliation, or strategy evaluation. | Possible historical decoder reference, but validate against official current and historical IDLs. |
| 56 | [TopTrenDev/pumpfun-copy-trading-bot-rust](https://github.com/TopTrenDev/pumpfun-copy-trading-bot-rust) | Prototype | Compact Rust copy-trading source. | No tests/CI, persistence, point-in-time target selection, fee/crowding analysis, or performance proof. | Copy trading is a prediction problem about the leader and a separate execution problem for the follower. |
| 57 | [mantodebilletes/Solana-Sniper-Bot](https://github.com/mantodebilletes/Solana-Sniper-Bot) | Shell | Describes sniper/autotrade capabilities. | README only; “best” claims are unauditable. | Require artifacts, not adjectives. |
| 58 | [DoradoDevs/solana-volume-bot](https://github.com/DoradoDevs/solana-volume-bot) | Misaligned component | Large full-stack system: PostgreSQL, Redis/BullMQ, workers, circuit breaker, Jito, encrypted wallet custody, Docker, architecture docs and two test-like files. | Explicit objective is generating on-chain volume with wallet fleets; not a predictive edge and potentially market-manipulative. Custodial/full-stack complexity creates a large security surface. | Useful adversarial specimen for detecting coordinated volume; do not copy its objective or custody design. |
| 59 | [TomatoRob/TomatosPump.funKOTHtradingBot](https://github.com/TomatoRob/TomatosPump.funKOTHtradingBot) | Fragment | Clear single-rule Python KOTH strategy. | One source file, tracks `.env`, no tests/simulator; KOTH status is public crowded information and does not establish post-fee expectancy. | Simple hypotheses are welcome only when evaluated across chronological regimes with realistic exits. |
| 60 | [xtoshi999/Pumpfun-Volume-Bot-TG](https://github.com/xtoshi999/Pumpfun-Volume-Bot-TG) | Misaligned fragment | Small Telegram volume automation. | One source file, artificial-volume goal, no tests or research evidence. | Detect its repeated cycles; never generate them. |
| 61 | [Vixxnu/Pump-Fun-bot](https://github.com/Vixxnu/Pump-Fun-bot) | Prototype | Python web UI, wallet, Pump API, Solana client, configurable auto-sell. | No tests/CI, third-party API dependence, committed bytecode artifacts, no research-grade data or executable validation. | Keep generated artifacts out of source control and make chain truth independent of convenience APIs. |

## Recurring failure modes

### 1. Execution mistaken for alpha

Most repositories implement some combination of:

```text
observe new token -> apply fixed filters -> buy -> poll price -> TP/SL sell
```

This proves transaction construction, not positive expectancy. Fixed holder counts, liquidity thresholds, KOTH status, migration, or a copied wallet are public signals. Their value must be estimated after crowding and costs.

### 2. No point-in-time research dataset

Nearly none preserve:

- What the bot knew at the decision timestamp.
- Which provider delivered each observation and when.
- Processed, confirmed, finalized, failed, expired, and orphaned distinctions.
- The historical creator/wallet statistics as they existed then.
- Every rejected candidate, not only purchased survivors.

Without rejected candidates and point-in-time histories, selection models acquire survivorship and look-ahead bias.

### 3. Unrealistic stops and exits

TP/SL configuration is common; executable exit modeling is rare. A stop is another Solana transaction competing with creator and holder sales. The quoted price can disappear before the sell lands, and available reserves can make the position partly or economically unsellable.

### 4. Copy-trading selection and lag ignored

Copy repositories typically ask the user for a target wallet but do not solve:

- How it was selected without hindsight.
- Whether its edge persists.
- Whether it is an insider, creator, service, or coordinated cluster.
- Whether followers crowd the same exit.
- Why its buys remain good after follower latency and price impact.
- Why copied sells can land before the price damage caused by the original sell.

### 5. “Anti-rug” reduced to raw thresholds

Raw holder counts and creator balances are easy to evade with linked wallets. Few projects model funding paths, coordinated timing, repeated co-entry, distribution behavior, or cluster-adjusted concentration. Unsupported accuracy claims are especially dangerous in a highly imbalanced and label-ambiguous problem.

### 6. No exact economic simulator

Dry mode often means “do not send,” and paper mode often means “use a displayed price.” Neither is enough. A credible simulator must insert the hypothetical transaction into observed order, apply exact integer curve/AMM math, fees, tips, compute budget, latency, failures, migration mechanics, and liquidity-constrained exits.

### 7. Protocol drift

Many repositories predate SOL/USDC pairs, v2 instructions, tiered fees, cashback, creator-sharing changes, Mayhem, or later account-layout changes. A bot can still compile while quoting or constructing economically/wire-level incorrect transactions.

Chainstack's repository stands out for documenting the April 2026 Pump account changes, but even there the authoritative source remains the official on-chain program/configuration and pinned official IDL revision.

### 8. Weak software assurance around real money

Only 7 of 61 snapshots contained repository-owned test files by the static path/name heuristic, and only 5 had GitHub Actions workflows. This does not measure test coverage or quality, but it is a warning that visible assurance artifacts are uncommon. Five tracked a root `.env`; several committed archives, generated bytecode, or `node_modules`. These visible practices are below the assurance expected for software holding signing authority.

### 9. Rebranding and SEO obscure provenance

Exact tree duplicates and obvious near-clones create the appearance of independent implementations. Stars, forks, repo count, and repeated claims cannot validate a technique without code lineage and independent experiments.

### 10. Artificial-volume tools contaminate signals

Volume/bump repositories demonstrate that wallet count, transaction count, buy/sell churn, and apparent activity can be manufactured. These projects are strategically useful as adversarial examples, but their behavior must not become part of our trading system.

## How our project should do better

### Build a research instrument before a trading product

Use one versioned canonical event schema for Jetstreamer backfill and live Geyser/Yellowstone ingestion. Preserve raw records, provider receipt timestamps, commitment transitions, exact instruction order, decoder version, and reconciliation status.

### Model related actors, not addresses

Build probabilistic wallet clusters from time-valid evidence:

- Funding convergence.
- Direct transfers.
- Repeated co-entry and coordinated timing.
- Position-size and transaction-construction fingerprints.
- Creator-fee sharing and linked distributions.
- Known service/exchange exclusions.

Calculate both raw and cluster-adjusted holder/flow features. Never assert common control from a single heuristic.

### Predict executable outcomes, not chart peaks

Estimate multiple competing outcomes:

- Return target reached before drawdown/stop.
- Dump hazard by time horizon.
- Graduation and post-graduation survival.
- Exit liquidity at our size.
- Expected latency-adjusted net return.
- Uncertainty/out-of-distribution probability.

### Make the simulator hostile

Replay exact integer math and actual ordering. Charge every fee/tip, sample empirically observed landing delay, model failures and blockhash expiry, constrain sells by liquidity, and stress simultaneous exits. Publish optimistic, executable, and stressed results separately.

### Evaluate chronologically and dependency-aware

- Freeze labels before optimizing models.
- Retain all candidates and decisions, including rejected tokens.
- Use purged walk-forward periods.
- Estimate uncertainty clustered by creator and funding group.
- Keep a final untouched chronological test.
- Compare against no-trade, random, fixed filters, momentum, graduation, and copy-wallet baselines.
- Require calibration and net expectancy, not accuracy or AUC alone.

### Separate six systems

```text
recorder -> canonical state -> point-in-time intelligence -> simulator/model
                                                           |
                                                           v
                                         independent risk veto -> execution
```

Signing, treasury, execution, and emergency risk controls must remain separate from research/model services. Missing or conflicting data means no trade.

### Treat competitors as component libraries and adversarial specimens

Potentially valuable ideas to study further:

- Chainstack: current Pump decoding, listener and transaction construction.
- Dexter: creator-history storage, operator workflow, paper/backtest surfaces.
- SOL BEAST: sender abstraction, dynamic priority fee, timeout and emergency controls.
- `adams...`: Rust venue separation and Jito examples.
- `greengod63`: raw transaction fixtures and listener tests.
- Volume bots: coordinated-wallet/volume fingerprints for detection only.

No competitor should be incorporated wholesale. Reimplement or vendor only pinned, licensed, reviewed components with tests and current official-protocol verification.

## Recommended next experiments

1. Define the canonical event schema and immutable decision record.
2. Benchmark Jetstreamer on a bounded Pump-heavy slot interval.
3. Reconcile every Pump transaction in a randomized sample against independent RPC data.
4. Construct golden fixtures covering current SOL/USDC, cashback, Mayhem, fee, PumpSwap, and failure regimes.
5. Replicate the most common public baselines—fixed filters, creator leaderboard, migration entry, KOTH, and copy wallet—inside our hostile simulator.
6. Measure which baselines remain positive after executable costs; expect many to fail.
7. Build cluster-adjusted variants and test whether they add stable out-of-sample value.
8. Begin continuous live recording before model development so latency and orphan behavior are observed rather than guessed.

## Bottom line

The public ecosystem offers plenty of ways to buy quickly and very little proof about what deserves to be bought. Our opportunity is not merely a faster sniper. It is a more scientific system that knows the provenance and timing of its data, recognizes coordinated actors, prices its own exit, refuses uncertain trades, and can demonstrate—without hindsight—that its expectancy survives execution.
