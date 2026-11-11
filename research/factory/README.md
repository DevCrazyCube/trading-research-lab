# FACTORY — the multi-asset strategy factory (started 2026-11-10)

Research and paper only. Nothing here places orders, holds keys or touches an account.

**Purpose.** Test many algorithms across FX, multi-asset ETFs and crypto with one harness: a design frozen and
hashed before the data is read, a declared trial count, sealed holdout windows read once, and costs taken from
named venues. Anything that survives goes to a forward paper logger, never straight to money.

## Status on 2026-11-11

**No strategy here is fundable.** Two crypto-perp books are being tested forward on paper. The first reading is
on 2027-01-09.

| What was tested | Result | Report |
|---|---|---|
| FACTORY v2, Tier 1: 16 pre-registered books on FX, multi-asset ETFs and crypto | 12 are not candidates, one cannot be traded at its cost, one is a composite of three books (Sharpe 0.21). The two crypto trend books are labelled PAPER-CANDIDATE and are the same 20 rules: net Sharpe 0.90, 22.4 % a year, worst drawdown −26.2 %, 2020-07 → 2026-11. | `reports/v2/RESULTS.md` |
| That crypto trend book, checked after the run | Fragile. Its 20 rules averaged a Sharpe of 0.48 on 2020-07 → 2023-12 and 0.05 on 2024-01 → 2026-11. One smoothing window moves the later Sharpe between −0.04 and +1.27. Eight days make up all of the later return. | `reports/v2/DIAGNOSTICS_POSTHOC.md` |
| FACTORY v2, Tier 2: a screen of 255 formulas | One survivor, `XSMOM.HIGH_PROXIMITY.L252` on crypto perps. On the sealed holdout its Sharpe is 0.99 with t 1.52: positive, not proven. | `reports/v2/RESULTS.md` |
| Retail realism and leverage | Accounts of EUR 1,000 to 10,000 simulated at Trading 212, Pepperstone, Kraken Derivatives and Bitvavo. At 10× the crypto trend book is ruined on 54 % of one-year paths, at 50× and 200× on all of them, and those figures are lower bounds. | `reports/v2/REALISM.md`, `reports/v2/LEVERAGE_LADDER.md` |
| FASTMOM v1: minute-scale momentum on BTC, ETH and SOL perps | Dead at real fees. 129 formula-symbol pairs, 6.4 million simulated trades, 2021 → 2023: every pair loses after costs. | `reports/fastmom_v1/FASTMOM_RESULTS.md` |

The post-hoc check was not pre-registered. It changes no label; it is the reason the label is not trusted.

## The forward paper test (FORWARD-CRYPTO v1)

A logger, live since 2026-11-11. Once a day at 01:20 UTC a systemd user timer on the owner's laptop runs
`python -m scripts.factory.forward_crypto run`. The job reads public Binance and Kraken market data, extends
the crypto-perp panel by the day that just closed, and appends ten rows to a hash-chained ledger: five frozen
books, each on an ideal account and on a USD 5,597 account limited to what Kraken Derivatives lists.

| Arm | Book |
|---|---|
| `A60` | the crypto trend book as registered (60-print volatility window) |
| `A30`, `A120` | the same book with 30- and 120-print windows |
| `A0` | the trend signal without volatility timing |
| `C252` | `XSMOM.HIGH_PROXIMITY.L252`, the Tier-2 survivor |

- **Rules:** `FORWARD_CRYPTO_v1_PREREGISTRATION.md`, frozen 2026-11-10 18:13 UTC, sha256 `9942631a…`.
- **Readings:** no statement about performance before 60 rows (2027-01-09). The pre-declared readings come at
  180 rows (2027-05-09).
- **Stop rule:** an arm that loses 30 % on its ideal account is frozen and recorded as failed.
- **What a reading triggers:** nothing by itself. Money, accounts and leverage stay the owner's decisions.
- **State:** `forward/crypto_v1/STATUS.md`. The first row is 2026-11-11: ten ledger rows, re-verified the
  same night. It shows only the cost of entering the books.
- **Timer, checks, removal, memory limits:** `scripts/factory/systemd/README.md`.

```sh
# from the repository root
sed -n '1,12p' research/factory/forward/crypto_v1/STATUS.md              # what the logger says
systemctl --user list-timers forward-crypto-v1.timer --no-pager          # next run
research/factory/.venv/bin/python -m scripts.factory.forward_crypto status   # ledger and hash chain; no network, no write
```

A failed run sends no notification. Look at `STATUS.md` and for `INCIDENT_*.json` files next to it.

## Frozen files: do not edit

The v2 runner and the forward logger re-hash these on every start and refuse to run on a mismatch (the logger
writes `INCIDENT:PINS`):

- `PREREGISTRATION_v2.md`, `DESIGN_v2.md`, `FORWARD_CRYPTO_v1_PREREGISTRATION.md`, `FASTMOM_PREREGISTRATION.md`
- `landscape/venues.json` and `data/<LANE>/manifest.json`
- everything under `scripts/factory/strategies/`, and in `scripts/factory/`: `panel.py`, `engine.py`,
  `stats.py`, `mtest.py`, `portfolio.py`, `realism.py`, `audit.py` and the runner `v2.py`

An improvement is a new pre-registered test with its own ledger, never an edit. The hashes are in
`PREREG_PIN_v2.json` and `forward/crypto_v1/PIN.json`, and in `DECISIONS.md`.

Known error in a frozen file: `landscape/venues.json` says Kraken Derivatives has a demo API. Kraken retired
it. The correction is at the top of `landscape/PLATFORMS.md`; no code reads that field.

## Layout

```
research/factory/
  README.md                                this file
  PREREGISTRATION_v2.md, DESIGN_v2.md      the frozen v2 design; PREREG_PIN_v2.json holds its hashes
  PREREGISTRATION_v1.md, PREREG_PIN.json   v1: superseded before any run, kept as written
  FASTMOM_PREREGISTRATION.md               the minute-scale momentum test
  FORWARD_CRYPTO_v1_PREREGISTRATION.md     the forward paper test
  requirements.txt                         the Python environment (.venv/ itself is not in git)
  data/<LANE>/                             frozen panels and manifests: FX, FX-FRED, FX-EXEC, MACRO,
                                           CRYPTO-PERP, CRYPTO-SPOT
  data/raw/                                downloads, 1.7 GB, not in git
  landscape/                               platforms, venues.json (costs and their sources), data sources,
                                           libraries, strategy classes
  landscape/evidence/                      saved source pages, 322 MB, not in git except the instrument
                                           lists the code reads
  runs/v2/, runs/fastmom_v1/               every run's full ledger: all formulas, winners and losers
  reports/v2/, reports/fastmom_v1/         the reports
  forward/crypto_v1/                       the forward test: ledger.jsonl, STATUS.md, stored raw responses
scripts/factory/
  panel.py engine.py stats.py mtest.py     the library
  portfolio.py realism.py audit.py
  strategies/                              78 declared rules (67 enabled) and the registry that counts them
  data/                                    loaders and panel builders
  v2.py, v2_extras.py                      the v2 runner: pin, tier2, mtest, freeze, tier1, fxrobust,
                                           holdout, report; realism and ladder
  fastmom.py                               the minute-momentum test
  forward_crypto.py                        the forward logger: run, status, replay
  systemd/                                 timer and service templates for the logger
  tests/                                   one test file per module
```

## Environment and tests

Python 3.12 in a `uv` virtual environment:

```sh
uv venv research/factory/.venv --python 3.12
uv pip install --python research/factory/.venv/bin/python -r research/factory/requirements.txt
research/factory/.venv/bin/python -m pytest scripts/factory/tests/test_forward_crypto.py -q   # 22 tests, about 95 s
```

Run one test file at a time on the owner's laptop: a run needs up to 0.8 GB and the machine stops processes
when memory runs short (`scripts/factory/systemd/README.md`, "Memory").

## Conventions

`DESIGN_v2.md` §3 and `PREREGISTRATION_v2.md` §3 are the authority. In short:

- **No look-ahead.** A target decided at one print is filled at a later print. The engine refuses `lag = 0`.
- **Future-scramble audit.** Each rule is re-run on a panel whose future is regenerated after a probe row. The
  rows up to the probe must come out bit-identical, or the rule is marked LEAKY and refused. A deliberately
  leaky control rule must fail this audit in the test suite.
- **Declared trials.** Every rule is registered with its full parameter grid, so the trial count is declared
  and not discovered. Every formula tried is written to the run ledger, winners and losers alike.
- **Sealed holdout.** The holdout was not read until the survivor list was frozen
  (`runs/v2/SURVIVORS_FROZEN.json`), and then once.
- **Costs are never zero.** They come from `landscape/venues.json`, with a stress scenario in every report.
- **No bare Sharpe.** A positive result is reported with its benchmark, its alpha against that benchmark, its
  turnover and its drawdown.

## Why this exists

Owner mandate of 2026-11-10: find a way to grow a portfolio in any market, long or short, by testing many
algorithms and automating the process. The earlier programme in this repository (2026-07 → 2026-10) found no
net-profitable bot in memecoins, US single-stock cross-sections, crypto carry and microstructure, or options.
It had tested FX carry, which it judged noise, and crypto time-series momentum, which did not hold up out of
sample. It had not tested FX trend,
cross-sectional momentum or value, and had never run a multi-asset risk-premia book. The first version of this
file said forex had never been tested; that was wrong for carry.
