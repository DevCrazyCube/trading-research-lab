#!/usr/bin/env python3
"""
AIRDROP / TGE DAY-ONE SUPPLY  --  event study, gated kill protocol.

Hypothesis under test
---------------------
The INITIAL (day-one / TGE) airdrop distribution puts free tokens into the hands of
recipients with ZERO COST BASIS and NO LOCKUP.  Unlike a vesting cliff -- where the
recipient is an insider or private-sale buyer with a cost basis and (usually) a
continuing relationship to the project -- an airdrop recipient is an anonymous farmer
whose entire position is profit at any price.  If that structural difference is real,
the market-controlled return from the first tradable close after the day-one airdrop
should be NEGATIVE over the following two weeks.

Distinct from the unlock-cliff short killed on 2026-09-03?
---------------------------------------------------------
The killed test read the `insiders` + `privateSale` cliff categories (n=545 / 311
clusters, mean +6.61%, wrong sign).  This test reads the `airdrop` category only, and
only each protocol's EARLIEST airdrop event.  The script measures the overlap in
(protocol, day) space and KILLS IMMEDIATELY if the populations are the same.

Method (fixed in advance, executed in order, stop at first failure)
------------------------------------------------------------------
  GATE 1  coverage census        -> minimum declared before counting
  GATE 2  power census           -> computed BEFORE any effect is read
  GATE 3  effect                 -> only if 1 and 2 pass
  ECONOMICS                      -> net of a measured round trip, explicit edge/cost

Control: the SAME-DAY CROSS-SECTIONAL MEDIAN return of the surviving perp universe
(this is the control that inverted the unlock-cliff result).  Built once, vectorized.
Cluster unit: event DATE.  Bootstrap: 5,000 draws, seed 20260903.

FREE data only.  Paper research.  No orders.
"""

import csv
import json
import glob
import os
import re
import sys
import datetime as dt

import numpy as np

# --------------------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------------------
REPO = "/home/anont/meme"
PANEL = os.path.join(REPO, "research/data/t23_cache/panel/perp_daily.csv")
UNLOCKS = os.path.join(REPO, "research/data/unlocks/*.json")
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
LLAMA_PROTOCOLS = os.path.join(CACHE, "llama_protocols2.json")
GECKO_MAP = os.path.join(CACHE, "gecko_id_to_symbol.json")

DAY_MS = 86_400_000

# --------------------------------------------------------------------------------------
# PRE-REGISTRATION -- printed before a single byte of return data is read.
# --------------------------------------------------------------------------------------
HOLD_DAYS = 14          # short at the first tradable close after the airdrop, cover +14d
CLAIMED_EFFECT_PP = 15.0  # "airdrop dump" lore: ~-15% in the first weeks, market-relative
KILL_LINE_MDE_PP = CLAIMED_EFFECT_PP / 2.0   # MDE must be strictly better than half
MIN_EVENTS = 120
MIN_CLUSTERS = 60
EFFECT_GATE_PP = -KILL_LINE_MDE_PP           # mean must be <= -7.5 pp
ICC = 0.30
ALPHA_Z = 1.6449         # one-sided alpha = 0.05
POWER_Z = 0.8416         # power = 0.80
BOOT_DRAWS = 5000
BOOT_SEED = 20260903
ROUND_TRIP_BP = 24.1     # this repo's own MEASURED two-perp round trip
SAME_POPULATION_KILL_FRAC = 0.50
COLLISION_GUARD_DAYS = 90


def prereg():
    print("=" * 88)
    print("PRE-REGISTRATION  --  frozen before any data is read")
    print("=" * 88)
    print(f"""
HYPOTHESIS (directional)
  The day-one / TGE airdrop hands free, unlocked, zero-cost-basis tokens to recipients
  with no continuing relationship to the project.  The market-controlled cumulative
  return from the first tradable perp close on/after that airdrop to +{HOLD_DAYS} calendar days
  is NEGATIVE.  Trade would be: short the perp at that close, cover {HOLD_DAYS} days later.

POPULATION
  For every protocol in the DefiLlama unlocks feed carrying at least one event with
  category == "airdrop", take that protocol's EARLIEST airdrop event.  One event per
  token, so the population ceiling equals the number of such protocols.

  DISCLOSURE: a raw category census was run before this pre-registration in order to
  confirm the category exists at all.  It returned 528 airdrop-category events across
  162 protocols (53,792 events total in the feed).  The ceiling of 162 was therefore
  KNOWN when the coverage minimum below was set.  Nothing about returns was read.

DISTINCTNESS REQUIREMENT (checked first)
  The unlock-cliff short killed 2026-09-03 read the insiders+privateSale cliff strata.
  If >= {SAME_POPULATION_KILL_FRAC:.0%} of the airdrop events here land on the same (protocol, day) as an
  insiders/privateSale cliff event of >= 1% of supply, this is the SAME POPULATION and
  is killed immediately by citation, with no further test.

CONTROL (mandatory)
  Same-day cross-sectional median simple return of the surviving perp universe, with
  any symbol inside its own event window excluded from the median.  Effect measured as
  the cumulative abnormal return CAR = sum over the {HOLD_DAYS} days of (r_symbol - r_median).

GATE 1  COVERAGE MINIMUM   (declared BEFORE counting)
  >= {MIN_EVENTS} tradable events across >= {MIN_CLUSTERS} distinct event-date clusters.
  Derivation, not a guess: this repo measured a 63.6 pp residual sd on alt-perp 44-day
  market-controlled windows.  Scaling by sqrt({HOLD_DAYS}/44) gives ~35.9 pp over {HOLD_DAYS} days.  A
  one-sample one-sided test at alpha=0.05, power=0.80 (z-sum {ALPHA_Z + POWER_Z:.4f}) needs
  n_eff >= (z_sum * sd / MDE)^2 = ({ALPHA_Z + POWER_Z:.4f} * 35.9 / {KILL_LINE_MDE_PP})^2 = {((ALPHA_Z + POWER_Z) * 35.9 / KILL_LINE_MDE_PP) ** 2:.0f}.
  {MIN_EVENTS} is set slightly below that as the floor at which the test could plausibly be
  powered if the realised sd comes in a little lower.  Below {MIN_EVENTS} the test cannot
  resolve the claimed effect and is dead on arrival -> KILL_COVERAGE.

GATE 2  POWER KILL LINE    (computed BEFORE any effect is read)
  Residual sd of the market-controlled CAR, clustered by event date with a conservative
  ICC = {ICC}, design effect = 1 + (mbar - 1) * ICC, n_eff = n / design effect.
  MDE = z_sum * sd / sqrt(n_eff).
  Claimed / plausible effect: {CLAIMED_EFFECT_PP:.1f} pp.  KILL unless MDE < {KILL_LINE_MDE_PP:.2f} pp.

GATE 3  EFFECT GATE        (read only if gates 1 and 2 both pass)
  Cluster bootstrap by event DATE, {BOOT_DRAWS} draws, seed {BOOT_SEED}.
  PASS requires ALL THREE:
    (a) mean CAR <= {EFFECT_GATE_PP:.1f} pp
    (b) bootstrap 95% CI upper bound < 0
    (c) net of the round trip below, mean still <= {EFFECT_GATE_PP / 2:.2f} pp
  Anything else -> KILL_EFFECT.

ECONOMICS
  Round trip = {ROUND_TRIP_BP} bp, this repo's own MEASURED two-perp cost.  Alt perps are
  worse, so this is the optimistic bound.  edge/cost ratio reported explicitly.
  An effect that cannot clear cost is dead regardless of its p-value.

NO THRESHOLD MOVES AFTER SEEING NUMBERS.  Stop at the first gate that fails.
""")
    print("=" * 88)
    print()


# --------------------------------------------------------------------------------------
# data loading
# --------------------------------------------------------------------------------------
def load_ticker_maps():
    """Objective protocol -> exchange ticker resolution.  No name-similarity heuristics:
    every mapping comes from an explicit id join (DefiLlama protocol id, or CoinGecko id)."""
    if not (os.path.exists(LLAMA_PROTOCOLS) and os.path.exists(GECKO_MAP)):
        sys.exit(f"missing ticker caches under {CACHE}")
    by_id = {}
    for p in json.load(open(LLAMA_PROTOCOLS))["protocols"]:
        s = (p.get("symbol") or "").strip()
        if s and s != "-" and p.get("defillamaId"):
            by_id[str(p["defillamaId"])] = s.upper()
    by_gecko = {k: v.upper() for k, v in json.load(open(GECKO_MAP)).items()}
    return by_id, by_gecko


def perp_base(sym):
    q = next((qq for qq in ("USDT", "USDC", "BUSD") if sym.endswith(qq)), None)
    if not q:
        return None
    b = sym[: -len(q)]
    m = re.match(r"^(1000000|100000|10000|1000|1M)(.+)$", b)
    if m:
        b = m.group(2)
    return b.upper()


def load_panel():
    """Returns (symbols, day_grid, close_matrix[sym, day])."""
    rows = []
    with open(PANEL) as f:
        r = csv.reader(f)
        next(r)
        for sym, day_ms, close, _qv, _tr in r:
            rows.append((sym, int(day_ms), float(close)))
    symbols = sorted({r[0] for r in rows})
    sidx = {s: i for i, s in enumerate(symbols)}
    d0 = min(r[1] for r in rows)
    d1 = max(r[1] for r in rows)
    ndays = (d1 - d0) // DAY_MS + 1
    close = np.full((len(symbols), ndays), np.nan, dtype=np.float64)
    for s, d, c in rows:
        close[sidx[s], (d - d0) // DAY_MS] = c
    return symbols, sidx, d0, ndays, close


def load_events(by_id, by_gecko):
    """Earliest airdrop-category event per protocol + the cliff population for the
    distinctness check."""
    airdrops = []       # dicts
    cliff_keys = set()  # (slug, day_index_ms) of insiders/privateSale cliffs >=1% of supply
    for path in sorted(glob.glob(UNLOCKS)):
        try:
            d = json.load(open(path))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        slug = os.path.basename(path)[:-5]
        md = d.get("metadata") or {}
        evs = md.get("events") or []
        if not evs:
            continue
        sm = d.get("supplyMetrics") or {}
        supply = sm.get("adjustedSupply") or sm.get("maxSupply") or 0.0

        def tok(e):
            n = e.get("noOfTokens") or []
            if not n:
                return 0.0
            return float(max(n)) if len(n) == 1 else float(max(n)) - float(min(n))

        for e in evs:
            if (e.get("category") in ("insiders", "privateSale")
                    and e.get("unlockType") == "cliff" and supply > 0
                    and tok(e) / supply >= 0.01):
                cliff_keys.add((slug, int(e["timestamp"]) // 86400 * 86400))

        ads = [e for e in evs if e.get("category") == "airdrop" and e.get("timestamp")]
        if not ads:
            continue
        first = min(ads, key=lambda e: e["timestamp"])
        ticker = None
        src = None
        for i in list(d.get("defillamaIds") or []) + ([d.get("pId")] if d.get("pId") else []):
            if str(i) in by_id:
                ticker, src = by_id[str(i)], "llamaId"
                break
        if ticker is None and d.get("gecko_id") in by_gecko:
            ticker, src = by_gecko[d["gecko_id"]], "geckoId"
        airdrops.append(dict(
            slug=slug, name=d.get("name"), ticker=ticker, src=src,
            ts=int(first["timestamp"]), tokens=tok(first), supply=supply,
            n_airdrop_events=len(ads),
            tge_proxy=min(int(e["timestamp"]) for e in evs if e.get("timestamp")),
            unlock_type=first.get("unlockType"),
        ))
    return airdrops, cliff_keys


# --------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------
def main():
    prereg()

    by_id, by_gecko = load_ticker_maps()
    symbols, sidx, d0, ndays, close = load_panel()
    print(f"[panel] {len(symbols)} perp symbols (delisted names included), "
          f"{ndays} day grid, "
          f"{dt.datetime.fromtimestamp(d0/1000, dt.UTC).date()} -> "
          f"{dt.datetime.fromtimestamp((d0+(ndays-1)*DAY_MS)/1000, dt.UTC).date()}")

    airdrops, cliff_keys = load_events(by_id, by_gecko)
    print(f"[feed]  {len(airdrops)} protocols carry >=1 airdrop-category event; "
          f"{len(cliff_keys)} insiders/privateSale cliffs >=1% of supply (the killed population)")

    # ---------------- distinctness against the already-killed cliff test ----------------
    same = sum(1 for a in airdrops
               if (a["slug"], a["ts"] // 86400 * 86400) in cliff_keys)
    frac = same / max(1, len(airdrops))
    print(f"\n[distinctness] first-airdrop events also present as an insiders/privateSale "
          f">=1% cliff on the same (protocol, day): {same}/{len(airdrops)} = {frac:.1%}")
    if frac >= SAME_POPULATION_KILL_FRAC:
        print(f"\n*** SAME POPULATION as the unlock-cliff short killed 2026-09-03 "
              f"({frac:.1%} >= {SAME_POPULATION_KILL_FRAC:.0%}). Killed by citation. ***")
        return
    print("[distinctness] populations are distinct -> the test is worth running.")

    # ---------------- GATE 1: coverage ----------------
    print("\n" + "=" * 88)
    print("GATE 1  COVERAGE CENSUS")
    print("=" * 88)

    bases = {}
    for s in symbols:
        b = perp_base(s)
        if b:
            bases.setdefault(b, []).append(s)

    first_day_idx = {}
    for s in symbols:
        row = close[sidx[s]]
        ok = np.flatnonzero(~np.isnan(row))
        if ok.size:
            first_day_idx[s] = int(ok[0])

    funnel = {"protocols with an airdrop event": len(airdrops)}
    step = [a for a in airdrops if a["ticker"]]
    funnel["ticker resolved by explicit id join"] = len(step)
    step = [a for a in step if a["tokens"] > 0]
    funnel["with a positive token amount"] = len(step)

    cand = []
    for a in step:
        picks = bases.get(a["ticker"], [])
        if not picks:
            continue
        # prefer USDT, then USDC, then BUSD; deterministic
        picks = sorted(picks, key=lambda s: ("USDT" not in s, "USDC" not in s, s))
        a = dict(a, symbol=picks[0])
        cand.append(a)
    funnel["ticker matches a Binance USD-M perp"] = len(cand)

    # objective ticker-collision guard: a perp cannot list long before its own token exists
    kept, collided = [], []
    for a in cand:
        fd = first_day_idx.get(a["symbol"])
        if fd is None:
            continue
        perp_first_ms = d0 + fd * DAY_MS
        if perp_first_ms < a["tge_proxy"] * 1000 - COLLISION_GUARD_DAYS * DAY_MS:
            collided.append(a)
        else:
            kept.append(a)
    funnel[f"survives ticker-collision guard (perp not listed >{COLLISION_GUARD_DAYS}d before token)"] = len(kept)
    if collided:
        print("  ticker-collision rejects (perp predates the token's own schedule):")
        for a in collided:
            print(f"    {a['slug']:<24} {a['ticker']:<8} {a['symbol']:<12} "
                  f"perp listed {dt.datetime.fromtimestamp((d0+first_day_idx[a['symbol']]*DAY_MS)/1000, dt.UTC).date()} "
                  f"vs token schedule start {dt.datetime.fromtimestamp(a['tge_proxy'], dt.UTC).date()}")

    # tradability: the perp must have a close on/after the event day that we can short,
    # and a full HOLD_DAYS of subsequent daily returns.
    events = []
    dropped_no_perp_yet, dropped_short_window = 0, 0
    for a in kept:
        ev_idx = (a["ts"] * 1000 - d0) // DAY_MS
        if ev_idx < 0 or ev_idx >= ndays:
            dropped_no_perp_yet += 1
            continue
        row = close[sidx[a["symbol"]]]
        # first tradable close on/after the event day
        fwd = np.flatnonzero(~np.isnan(row[ev_idx:]))
        if fwd.size == 0:
            dropped_no_perp_yet += 1
            continue
        entry = ev_idx + int(fwd[0])
        if entry + HOLD_DAYS >= ndays or np.isnan(row[entry:entry + HOLD_DAYS + 1]).any():
            dropped_short_window += 1
            continue
        a = dict(a, ev_idx=ev_idx, entry=entry, lag=entry - ev_idx)
        events.append(a)
    funnel[f"has a tradable close and a full +{HOLD_DAYS}d window"] = len(events)

    print()
    for k, v in funnel.items():
        print(f"  {k:<70} {v:>5}")
    print(f"  (dropped: {dropped_no_perp_yet} perp never traded on/after the event, "
          f"{dropped_short_window} incomplete {HOLD_DAYS}d window)")

    clusters = sorted({e["entry"] for e in events})
    n, k = len(events), len(clusters)
    if n:
        lags = np.array([e["lag"] for e in events])
        sizes = np.array([e["tokens"] / e["supply"] for e in events if e["supply"] > 0])
        print(f"\n  n = {n} events, {k} distinct event-date clusters, "
              f"{len({e['slug'] for e in events})} distinct tokens")
        print(f"  entry lag after the airdrop timestamp: median {np.median(lags):.0f}d, "
              f"max {lags.max():.0f}d  ({(lags == 0).sum()} enter on the airdrop day itself)")
        if sizes.size:
            print(f"  airdrop size as a share of supply: median {np.median(sizes):.2%}, "
                  f"n with supply known {sizes.size}")

    print(f"\n  DECLARED MINIMUM: {MIN_EVENTS} events / {MIN_CLUSTERS} clusters")
    if n < MIN_EVENTS or k < MIN_CLUSTERS:
        print(f"  -> GATE 1 FAILS ({n} < {MIN_EVENTS} events)"
              if n < MIN_EVENTS else f"  -> GATE 1 FAILS ({k} < {MIN_CLUSTERS} clusters)")
        print("\n" + "*" * 88)
        print("VERDICT: KILL_COVERAGE.  The population ceiling is one day-one airdrop per")
        print("protocol, and the feed simply does not contain enough of them that are")
        print("tradable on this venue.  No effect is read.  Stopping here, by protocol.")
        print("*" * 88)
        report_ceiling(airdrops, cand, events, n, k)
        post_kill_power_diagnostic(events, symbols, sidx, close, ndays)
        return
    print("  -> GATE 1 PASSES")

    # ---------------- market control: built ONCE, vectorized ----------------
    ret = np.full_like(close, np.nan)
    ret[:, 1:] = close[:, 1:] / close[:, :-1] - 1.0

    masked = ret.copy()
    for e in events:
        masked[sidx[e["symbol"]], e["entry"]: e["entry"] + HOLD_DAYS + 1] = np.nan
    with np.errstate(all="ignore"):
        med = np.nanmedian(masked, axis=0)
    med = np.nan_to_num(med, nan=0.0)
    breadth = (~np.isnan(masked)).sum(axis=0)

    car = np.array([
        float(np.sum(ret[sidx[e["symbol"]], e["entry"] + 1: e["entry"] + HOLD_DAYS + 1]
                     - med[e["entry"] + 1: e["entry"] + HOLD_DAYS + 1])) * 100.0
        for e in events
    ])
    ev_days = np.array([e["entry"] for e in events])
    print(f"\n[control] same-day cross-sectional median built once over the whole grid; "
          f"median daily breadth {int(np.median(breadth[breadth > 0]))} symbols")

    # ---------------- GATE 2: power, BEFORE the effect ----------------
    print("\n" + "=" * 88)
    print("GATE 2  POWER CENSUS  (computed before any effect is read)")
    print("=" * 88)
    sd = float(np.std(car, ddof=1))
    _, counts = np.unique(ev_days, return_counts=True)
    mbar = float(counts.mean())
    deff = 1.0 + (mbar - 1.0) * ICC
    n_eff = n / deff
    mde = (ALPHA_Z + POWER_Z) * sd / np.sqrt(n_eff)
    print(f"  residual sd of the market-controlled {HOLD_DAYS}d CAR   {sd:8.2f} pp")
    print(f"  events / clusters                          {n} / {k}   (mean cluster size {mbar:.2f})")
    print(f"  design effect at ICC={ICC}                    {deff:8.3f}")
    print(f"  effective n                                {n_eff:8.1f}")
    print(f"  MDE (alpha=0.05 one-sided, power=0.80)     {mde:8.2f} pp")
    print(f"  DECLARED KILL LINE                         {KILL_LINE_MDE_PP:8.2f} pp "
          f"(half of the {CLAIMED_EFFECT_PP:.0f} pp claim)")
    if mde >= KILL_LINE_MDE_PP:
        print(f"  -> GATE 2 FAILS: MDE {mde:.2f} pp cannot resolve a {CLAIMED_EFFECT_PP:.0f} pp claim.")
        print("\n" + "*" * 88)
        print("VERDICT: KILL_POWER.  No effect is read.  Stopping here, by protocol.")
        print("*" * 88)
        return
    print("  -> GATE 2 PASSES")

    # ---------------- GATE 3: effect ----------------
    print("\n" + "=" * 88)
    print("GATE 3  EFFECT  (cluster bootstrap by event date)")
    print("=" * 88)
    rng = np.random.default_rng(BOOT_SEED)
    uniq = np.unique(ev_days)
    groups = [car[ev_days == u] for u in uniq]
    boots = np.empty(BOOT_DRAWS)
    for i in range(BOOT_DRAWS):
        pick = rng.integers(0, len(groups), len(groups))
        boots[i] = np.concatenate([groups[j] for j in pick]).mean()
    lo, hi = np.percentile(boots, [2.5, 97.5])
    p_sign = float((boots >= 0).mean())          # P(the mean is NOT negative)
    mean, median = float(car.mean()), float(np.median(car))
    print(f"  mean CAR                {mean:+8.2f} pp")
    print(f"  median CAR              {median:+8.2f} pp")
    print(f"  95% cluster-boot CI     [{lo:+.2f}, {hi:+.2f}] pp")
    print(f"  P(mean >= 0)            {p_sign:8.4f}")
    print(f"  P(mean <  0)            {1 - p_sign:8.4f}")
    print(f"  win rate (CAR < 0)      {(car < 0).mean():8.1%}")

    cost_pp = ROUND_TRIP_BP / 100.0
    net = mean + cost_pp                          # a short pays the cost, shrinking the gain
    a_ok, b_ok, c_ok = mean <= EFFECT_GATE_PP, hi < 0, net <= EFFECT_GATE_PP / 2
    print(f"\n  gate (a) mean <= {EFFECT_GATE_PP:.1f} pp      {'PASS' if a_ok else 'FAIL'}")
    print(f"  gate (b) CI upper < 0        {'PASS' if b_ok else 'FAIL'}")
    print(f"  gate (c) net <= {EFFECT_GATE_PP/2:.2f} pp     {'PASS' if c_ok else 'FAIL'}")

    print("\n" + "=" * 88)
    print("ECONOMICS")
    print("=" * 88)
    print(f"  gross mean edge         {abs(mean):8.2f} pp = {abs(mean)*100:.0f} bp")
    print(f"  measured round trip     {cost_pp:8.2f} pp = {ROUND_TRIP_BP:.1f} bp")
    print(f"  net mean                {net:+8.2f} pp")
    print(f"  edge / cost ratio       {abs(mean)*100/ROUND_TRIP_BP:8.2f}x")
    verdict = "SURVIVES" if (a_ok and b_ok and c_ok) else "KILL_EFFECT"
    print(f"\n*** VERDICT: {verdict} ***")


def report_ceiling(airdrops, cand, events, n, k):
    print("\n  where the population went, in one line each:")
    print(f"    {len(airdrops):>4}  protocols in the free vesting feed with any airdrop event")
    print(f"    {len(cand):>4}  of those resolve to a ticker that is a Binance USD-M perp base")
    print(f"    {n:>4}  of those have a tradable perp close on/after the day-one airdrop"
          f" plus a full window ({k} clusters)")
    if events:
        yrs = {}
        for e in events:
            y = dt.datetime.fromtimestamp(e["ts"], dt.UTC).year
            yrs[y] = yrs.get(y, 0) + 1
        print("    surviving events by year: " + ", ".join(f"{y}:{c}" for y, c in sorted(yrs.items())))


def post_kill_power_diagnostic(events, symbols, sidx, close, ndays):
    """Runs AFTER the coverage kill has already fired.  Its only purpose is to ask whether
    the kill is an artifact of where the coverage line was drawn.  It computes the residual
    sd and the MDE at the realised n -- gate-2 quantities, which are by construction blind
    to the effect.  The mean/median/CI are NOT computed or printed: gate 1 killed the test
    and the effect stays unread, by protocol."""
    if not events:
        return
    print("\n" + "-" * 88)
    print("POST-KILL DIAGNOSTIC (power only -- the effect is NOT read)")
    print("-" * 88)

    strict = [e for e in events if e["lag"] <= 3]
    print(f"  Of the {len(events)} events, only {len(strict)} are genuinely 'day-one': the perp had a")
    print(f"  tradable close within 3 days of the airdrop.  The rest are airdrops whose perp did")
    print(f"  not exist yet (entry lag up to {max(e['lag'] for e in events)}d), so they are not day-one")
    print(f"  supply trades at all.  On the hypothesis as stated, usable n is {len(strict)}, not {len(events)}.")

    ret = np.full_like(close, np.nan)
    ret[:, 1:] = close[:, 1:] / close[:, :-1] - 1.0
    masked = ret.copy()
    for e in events:
        masked[sidx[e["symbol"]], e["entry"]: e["entry"] + HOLD_DAYS + 1] = np.nan
    with np.errstate(all="ignore"):
        med = np.nan_to_num(np.nanmedian(masked, axis=0), nan=0.0)

    for label, evs in (("all tradable", events), ("strict day-one (lag<=3d)", strict)):
        if not evs:
            continue
        car = np.array([
            float(np.sum(ret[sidx[e["symbol"]], e["entry"] + 1: e["entry"] + HOLD_DAYS + 1]
                         - med[e["entry"] + 1: e["entry"] + HOLD_DAYS + 1])) * 100.0
            for e in evs
        ])
        days = np.array([e["entry"] for e in evs])
        sd = float(np.std(car, ddof=1))
        _, counts = np.unique(days, return_counts=True)
        mbar = float(counts.mean())
        deff = 1.0 + (mbar - 1.0) * ICC
        n_eff = len(evs) / deff
        mde = (ALPHA_Z + POWER_Z) * sd / np.sqrt(n_eff)
        print(f"\n  [{label}]  n={len(evs)}, clusters={len(counts)}, mean cluster size {mbar:.2f}")
        print(f"    residual sd of the {HOLD_DAYS}d market-controlled CAR   {sd:7.2f} pp")
        print(f"    design effect at ICC={ICC} / effective n            {deff:.3f} / {n_eff:.1f}")
        print(f"    MDE at alpha=0.05 one-sided, power=0.80        {mde:7.2f} pp"
              f"   vs the {KILL_LINE_MDE_PP:.2f} pp kill line -> "
              f"{'would also FAIL gate 2' if mde >= KILL_LINE_MDE_PP else 'would have passed gate 2'}")
        print(f"    n needed for MDE < {KILL_LINE_MDE_PP:.2f} pp at this sd:        "
              f"{((ALPHA_Z + POWER_Z) * sd / KILL_LINE_MDE_PP) ** 2 * deff:7.0f} events")
    print("\n  The effect (mean / median / CI) is deliberately left unread: gate 1 failed.")


if __name__ == "__main__":
    main()
