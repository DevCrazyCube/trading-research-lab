#!/usr/bin/env python3
"""
DELISTING FORCED EXIT -- event study on Binance USD-M perps.

HYPOTHESIS
    A delisting announcement forces every holder to close by a contractual deadline.
    That is pure forced flow with a known date, so the market-controlled return over
    the final 30 / 14 / 7 days of a doomed contract should be systematically negative,
    and should be short-able.

METHOD (fixed, applied in order, stop at the first failure)
    GATE 0  measurement validity -- can the panel even identify the event date?
    GATE 1  coverage             -- enough usable events / clusters?
    GATE 2  power                -- MDE computed BEFORE any effect is read
    GATE 3  effect               -- cluster bootstrap by event date
    ECONOMICS                    -- net of a realistic perp round trip

FREE DATA ONLY. PAPER-ONLY RESEARCH. New file; touches nothing in arena/.
"""

import csv
import calendar
import datetime as dt
import math
import os
import sys

import numpy as np

PANEL = "/home/anont/meme/research/data/t23_cache/panel/perp_daily.csv"

SEED = 20260903
ALPHA = 0.05            # one-sided
POWER = 0.80
ICC = 0.30              # conservative, mandated
Z_ALPHA = 1.6448536269514722   # Phi^-1(0.95)
Z_POWER = 0.8416212335729143   # Phi^-1(0.80)

WINDOWS = (30, 14, 7)
PRIMARY_WINDOW = 30

# ---- repo-measured cost, not assumed -------------------------------------
ROUND_TRIP_BP = 24.1    # this repo's own measured two-perp round trip.
                        # Alt perps are strictly worse; a delisting tape is worse
                        # again. So every ratio below is an UPPER BOUND on the truth.
COST_MULTIPLE_REQUIRED = 5.0   # an edge must be >= 5x cost to be worth carrying


def rule(ch="="):
    print(ch * 78)


# =========================================================================
# PRE-REGISTRATION -- printed BEFORE a single byte of the panel is read
# =========================================================================
def prereg():
    rule()
    print("PRE-REGISTRATION  (declared BEFORE any data is read)")
    rule()
    print("""
HYPOTHESIS (directional)
  Perp contracts approaching a delisting deadline earn a NEGATIVE market-controlled
  return over their final trading days, because holders are contractually forced to
  close and the flow is one-sided (long-liquidation dominant).

EVENT DEFINITION
  The last observed trading day of a symbol whose series stops before the panel's
  terminal day.

  PRIMARY ARM ("clean stops"): only symbols whose series ends MID-CALENDAR-MONTH.
    The panel is assembled from Binance MONTHLY archive zips. A symbol whose final
    month is PARTIAL proves the archive published a truncated month, i.e. the last
    bar really is the last trading day. A symbol whose final month is COMPLETE is
    archive-truncation-ambiguous: its true stop date is unknown to as much as +31
    days, so its "final 30 days" window is not its final 30 days.

  ROBUSTNESS ARM ("all stops"): every symbol that stops, including the ambiguous
    month-boundary enders. Declared here, in advance, precisely so that the verdict
    cannot be an artifact of the primary arm's exclusion rule. If the primary arm
    dies on coverage, the robustness arm is still carried through gate 2 to show
    whether the design would have had power even with every stop included.

CONTROL (mandatory)
  Same-day cross-sectional MEDIAN log return of the entire surviving universe,
  subtracted from every symbol-day. This is the control that inverted the unlock-
  cliff result from -8%/-15% to +6.61% mean on 2026-09-03.

GATE 1 -- COVERAGE MINIMUM (all three must hold, primary arm)
  (a) n_events  >= 40
  (b) n_clusters (distinct event DATES) >= 20
  (c) largest single event-date cluster <= 30% of events
  Rationale, from method not from data: a cluster bootstrap is not trustworthy
  below ~20 clusters, and a single dominant cluster makes the nominal n fictitious
  -- this repo already retired a 598-formula survivor that was a 3-coin artifact
  with 44.9% of held-out P&L in its top 3 names.

GATE 2 -- POWER KILL LINE (computed BEFORE any effect is read)
  Plausible/claimed effect, set GENEROUSLY in the trade's favour (a larger claim
  makes this gate EASIER to pass, so it biases against killing):
      30d window: claim -20 pp   -> kill unless MDE < 10.0 pp
      14d window: claim -12 pp   -> kill unless MDE <  6.0 pp
       7d window: claim  -8 pp   -> kill unless MDE <  4.0 pp
  PRIMARY window is 30d. Residual sd is taken from a PLACEBO sample of non-event
  symbol-windows (seed 20260903), so computing it cannot peek at the real events.
  Design effect = 1 + (mean cluster size - 1) * ICC, ICC = 0.30.
  MDE = (z_0.95 + z_0.80) * sd / sqrt(n_eff), n_eff = n / DEFF.

GATE 3 -- EFFECT (only if gates 1 and 2 both pass)
  Cluster-bootstrap by event DATE, 5,000 draws, fixed seed 20260903.
  Report mean, median, CI, P(sign<0). Gate: the 95% CI upper bound must be < 0
  AND the point estimate must clear economics below.

ECONOMICS
  Round trip = 24.1 bp (this repo's own MEASURED two-perp round trip). Alt perps
  and a delisting tape are strictly worse, so the edge/cost ratio reported is an
  UPPER BOUND. An edge must be >= 5x cost to be worth carrying.

STOPPING RULE
  Stop at the FIRST failing gate. Do not tune a threshold after seeing a number.
  Do not search for a surviving variant.
""")
    rule()
    print()


# =========================================================================
# DATA
# =========================================================================
def load_panel(path):
    """Return (symbols, days, CLOSE[n_sym, n_day]) with NaN where absent."""
    syms, days = {}, {}
    rows = []
    with open(path, newline="") as fh:
        rd = csv.reader(fh)
        header = next(rd)
        assert header[:3] == ["symbol", "day_ms", "close"], header
        for r in rd:
            s, d = r[0], int(r[1])
            try:
                c = float(r[2])
            except ValueError:
                continue
            if not (c > 0):
                continue
            if s not in syms:
                syms[s] = len(syms)
            if d not in days:
                days[d] = None
            rows.append((syms[s], d, c))
    day_list = sorted(days)
    dix = {d: i for i, d in enumerate(day_list)}
    sym_list = [None] * len(syms)
    for s, i in syms.items():
        sym_list[i] = s
    C = np.full((len(sym_list), len(day_list)), np.nan, dtype=np.float64)
    for si, d, c in rows:
        C[si, dix[d]] = c
    return sym_list, np.array(day_list, dtype=np.int64), C


def to_date(ms):
    return dt.datetime.fromtimestamp(int(ms) / 1000, dt.UTC).date()


def build_excess(C):
    """Vectorized ONCE: log returns, same-day cross-sectional median, excess."""
    with np.errstate(divide="ignore", invalid="ignore"):
        L = np.log(C)
    R = np.full_like(L, np.nan)
    R[:, 1:] = L[:, 1:] - L[:, :-1]          # NaN wherever either close is absent
    med = np.nanmedian(R, axis=0)            # same-day cross-sectional median, ONE pass
    med = np.where(np.isfinite(med), med, 0.0)
    E = R - med[None, :]
    return R, med, E


def window_sums(E, K):
    """O(1) window lookup: (cum_excess, cum_valid) prefix sums along time."""
    valid = np.isfinite(E)
    Ez = np.where(valid, E, 0.0)
    cs = np.concatenate([np.zeros((E.shape[0], 1)), np.cumsum(Ez, axis=1)], axis=1)
    cv = np.concatenate([np.zeros((E.shape[0], 1)), np.cumsum(valid, axis=1)], axis=1)
    return cs, cv


def win_stat(cs, cv, si, end_col, K):
    """Excess cum log return over the K return-days ending at end_col inclusive.
    Requires all K to be valid; else None."""
    a = end_col - K + 1
    if a < 0:
        return None
    n_valid = cv[si, end_col + 1] - cv[si, a]
    if n_valid < K:
        return None
    return cs[si, end_col + 1] - cs[si, a]


# =========================================================================
# GATE 0 -- measurement validity
# =========================================================================
def gate0(sym_list, day_list, C):
    rule()
    print("GATE 0  MEASUREMENT VALIDITY -- can the panel identify the event at all?")
    rule()
    panel_end_col = C.shape[1] - 1
    panel_end = to_date(day_list[-1])
    last_col = np.full(len(sym_list), -1, dtype=np.int64)
    for i in range(len(sym_list)):
        idx = np.flatnonzero(np.isfinite(C[i]))
        last_col[i] = idx[-1] if idx.size else -1

    stops, clean, ambiguous = [], [], []
    for i, s in enumerate(sym_list):
        lc = int(last_col[i])
        if lc < 0 or lc >= panel_end_col:
            continue                                  # still alive at panel end
        d = to_date(day_list[lc])
        dim = calendar.monthrange(d.year, d.month)[1]
        n_in_final_month = int(np.sum(
            [to_date(day_list[c]).year == d.year and to_date(day_list[c]).month == d.month
             for c in np.flatnonzero(np.isfinite(C[i]))]))
        rec = (i, s, lc, d, n_in_final_month, dim)
        stops.append(rec)
        if d.day == dim and n_in_final_month == dim:
            ambiguous.append(rec)
        else:
            clean.append(rec)

    print(f"  panel: {len(sym_list)} symbols, {len(day_list)} days, "
          f"{to_date(day_list[0])} -> {panel_end}")
    print(f"  symbols still trading on the panel's terminal day : {len(sym_list)-len(stops)}")
    print(f"  symbols that STOP before it (candidate delistings): {len(stops)}")
    print(f"    ends MID-month, final month PARTIAL   (clean)    : {len(clean)}")
    print(f"    ends ON a complete calendar month-end (ambiguous): {len(ambiguous)}")
    print()
    print("  PROVENANCE: the panel is assembled from Binance MONTHLY archive zips")
    print("  (data/futures/um/monthly/klines/{SYM}/1d/{SYM}-1d-YYYY-MM.zip). A symbol")
    print("  that genuinely stopped mid-month leaves a PARTIAL final month. A symbol")
    print(f"  whose final month is COMPLETE ({len(ambiguous)} of {len(stops)} = "
          f"{100*len(ambiguous)/max(1,len(stops)):.1f}%) has an event date that is")
    print("  unknown to as much as +31 days.")
    print()
    print("  ANNOUNCEMENT vs FINAL TRADING DAY: the panel carries symbol, day, close,")
    print("  quote_volume, trades -- and nothing else. No announcement field exists in")
    print("  it or in any other on-disk free dataset in this repo. The forced flow the")
    print("  hypothesis is about begins at the ANNOUNCEMENT, not at the final bar, and")
    print("  that date is UNOBSERVABLE here. The best this panel can do is a window")
    print("  anchored on the deadline, which mixes pre-announcement days (no forced")
    print("  flow) into the same average as post-announcement days (all the flow).")
    print("  That is an attenuation bias of unknown size, toward zero.")
    print()
    print("  EX-ANTE TRADEABILITY (the limitation that outranks every gate below):")
    print("  every window in this study is anchored on a date that is knowable ONLY")
    print("  IN HINDSIGHT. The 'final 30 days' of a contract can be identified only")
    print("  after the contract has already stopped printing. To actually put on the")
    print("  short you would need the announcement, in advance -- and the announcement")
    print("  is the one field this panel does not have, for any of the events, in")
    print("  either arm. So even an arm that clears every statistical gate below would")
    print("  describe a hindsight-anchored window, not an executable trade. Buying a")
    print("  real delisting-announcement calendar is a PRECONDITION for this test, not")
    print("  a refinement of it.")
    print()
    return stops, clean, ambiguous


# =========================================================================
# GATE 1 -- coverage
# =========================================================================
def gate1(name, recs, min_n, min_clusters, max_share):
    rule()
    print(f"GATE 1  COVERAGE -- {name}")
    rule()
    dates = [r[3] for r in recs]
    uniq = sorted(set(dates))
    counts = {d: dates.count(d) for d in uniq}
    biggest = max(counts.values()) if counts else 0
    biggest_d = max(counts, key=counts.get) if counts else None
    n, k = len(recs), len(uniq)
    share = biggest / n if n else 1.0
    print(f"  events (n)                     : {n}      (minimum {min_n})")
    print(f"  distinct event-date clusters   : {k}      (minimum {min_clusters})")
    print(f"  largest cluster                : {biggest} on {biggest_d} "
          f"= {100*share:.1f}%   (maximum {100*max_share:.0f}%)")
    print(f"  mean cluster size              : {n/k:.2f}" if k else "  mean cluster size: n/a")
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:6]
    print(f"  top clusters                   : {[(str(d), c) for d, c in top]}")
    ok_n, ok_k, ok_s = n >= min_n, k >= min_clusters, share <= max_share
    print(f"  -> n>={min_n}: {'PASS' if ok_n else 'FAIL'} | "
          f"clusters>={min_clusters}: {'PASS' if ok_k else 'FAIL'} | "
          f"concentration<={100*max_share:.0f}%: {'PASS' if ok_s else 'FAIL'}")
    verdict = ok_n and ok_k and ok_s
    print(f"  GATE 1 {'PASS' if verdict else 'FAIL'}")
    print()
    return verdict, n, k, biggest, share, counts


# =========================================================================
# GATE 2 -- power (residual sd from PLACEBO windows; no peek at events)
# =========================================================================
def placebo_sd(E, cs, cv, C, last_col, K, n_draws=20000, rng=None):
    """Residual sd of the market-controlled K-day cumulative excess log return,
    sampled from NON-EVENT symbol-windows (>= 40 days before any symbol's stop)."""
    rng = rng or np.random.default_rng(SEED)
    n_sym, n_day = E.shape
    out = []
    tries = 0
    while len(out) < n_draws and tries < n_draws * 40:
        tries += 1
        si = int(rng.integers(0, n_sym))
        lc = int(last_col[si])
        if lc < K + 40:
            continue
        end = int(rng.integers(K - 1, lc - 40 + 1))   # keep 40d clear of the stop
        v = win_stat(cs, cv, si, end, K)
        if v is None:
            continue
        out.append(v)
    a = np.array(out)
    return a


# =========================================================================
# GATE 3 -- effect (only reached if 1 and 2 pass)
# =========================================================================
def gate3(name, recs, cs, cv, K, n_boot=5000):
    rule()
    print(f"GATE 3  EFFECT -- {name}, {K}d window")
    rule()
    obs, dates = [], []
    for (si, s, lc, d, _n, _dim) in recs:
        v = win_stat(cs, cv, si, lc, K)
        if v is None:
            continue
        obs.append(v)
        dates.append(d)
    obs = np.array(obs)
    dates = np.array([str(x) for x in dates])
    uniq = np.unique(dates)
    groups = [obs[dates == u] for u in uniq]
    rng = np.random.default_rng(SEED)
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        means[b] = np.concatenate([groups[i] for i in pick]).mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    to_pp = lambda x: 100.0 * math.expm1(x)
    print(f"  n usable = {len(obs)}, clusters = {len(uniq)}")
    print(f"  mean   = {to_pp(obs.mean()):+.2f} pp")
    print(f"  median = {to_pp(float(np.median(obs))):+.2f} pp")
    print(f"  cluster-bootstrap 95% CI = [{to_pp(lo):+.2f}, {to_pp(hi):+.2f}] pp")
    print(f"  P(mean < 0) = {float(np.mean(means < 0)):.4f}")
    print()
    return obs, means, lo, hi


# =========================================================================
# ECONOMICS
# =========================================================================
def economics(mde_pp, effect_pp=None):
    rule()
    print("ECONOMICS")
    rule()
    cost_pp = ROUND_TRIP_BP / 100.0
    need_pp = COST_MULTIPLE_REQUIRED * cost_pp
    print(f"  measured two-perp round trip     : {ROUND_TRIP_BP:.1f} bp = {cost_pp:.3f} pp")
    print(f"  alt perps / delisting tape       : strictly worse (unmeasured); every")
    print(f"                                     ratio below is an UPPER BOUND.")
    print(f"  edge needed to be worth carrying : {COST_MULTIPLE_REQUIRED:.0f}x cost = {need_pp:.2f} pp")
    print()
    if effect_pp is not None:
        print(f"  measured effect                  : {effect_pp:+.2f} pp")
        print(f"  edge/cost ratio                  : {abs(effect_pp)/cost_pp:.2f}x")
    else:
        print(f"  measured effect                  : NOT REACHED (an earlier gate killed it)")
        print(f"  smallest effect this design could detect (MDE) : {mde_pp:.2f} pp")
        print(f"  MDE / round-trip cost            : {mde_pp/cost_pp:.1f}x")
        print(f"  MDE / economically-sufficient edge ({need_pp:.2f} pp) : "
              f"{mde_pp/need_pp:.1f}x")
        print()
        print("  READ THIS THE RIGHT WAY ROUND. The design cannot see anything smaller")
        print(f"  than {mde_pp:.2f} pp, but a trade only needs {need_pp:.2f} pp to be worth doing.")
        print(f"  The whole economically interesting band -- {need_pp:.2f} pp up to "
              f"{mde_pp:.2f} pp --")
        print("  is INVISIBLE to this dataset. A null here is not evidence of no edge;")
        print("  it is evidence that this panel cannot answer the question either way.")
    print()


def main():
    prereg()

    print("reading panel ...")
    sym_list, day_list, C = load_panel(PANEL)
    R, med, E = build_excess(C)
    print(f"  loaded {C.shape[0]} symbols x {C.shape[1]} days; "
          f"cross-sectional median control built once, vectorized.")
    print()

    last_col = np.array([
        (np.flatnonzero(np.isfinite(C[i]))[-1] if np.isfinite(C[i]).any() else -1)
        for i in range(C.shape[0])], dtype=np.int64)

    stops, clean, ambiguous = gate0(sym_list, day_list, C)

    kill_lines = {30: 10.0, 14: 6.0, 7: 4.0}

    # ---------------- PRIMARY ARM ----------------
    ok1, n1, k1, big1, share1, _ = gate1("PRIMARY ARM (clean mid-month stops)",
                                         clean, 40, 20, 0.30)

    cs30, cv30 = window_sums(E, PRIMARY_WINDOW)
    cs_all = {K: window_sums(E, K) for K in WINDOWS}

    if not ok1:
        print("!! PRIMARY ARM KILLED AT GATE 1 (COVERAGE). Stopping the primary line.")
        print("   Per the stopping rule, gate 3 is NOT run on the primary arm.")
        print()
        # Gate 2 is still computed for BOTH arms: it uses only PLACEBO windows,
        # never the real event outcomes, so it cannot be a peek. It is reported so
        # the verdict cannot be dismissed as an artifact of the exclusion rule.
        print("   Carrying the PRE-DECLARED robustness arm through gate 1 and gate 2")
        print("   so the kill is not attributable to the primary arm's exclusion rule.")
        print()

    ok1b, n1b, k1b, big1b, share1b, _ = gate1(
        "ROBUSTNESS ARM (all stops, incl. ambiguous month-end enders)",
        stops, 40, 20, 0.30)

    def run_gate2(name, recs, n, k):
        Kw = {K: cs_all[K] for K in WINDOWS}
        rule()
        print(f"GATE 2  POWER -- {name}   (computed BEFORE any effect is read)")
        rule()
        rng = np.random.default_rng(SEED)
        mean_cluster = n / k
        deff = 1.0 + (mean_cluster - 1.0) * ICC
        n_eff = n / deff
        print(f"  n = {n}, clusters = {k}, mean cluster size = {mean_cluster:.2f}")
        print(f"  design effect = 1 + ({mean_cluster:.2f}-1)*{ICC} = {deff:.3f}")
        print(f"  effective n   = {n} / {deff:.3f} = {n_eff:.1f}")
        res = {}
        for K in WINDOWS:
            cs, cv = Kw[K]
            a = placebo_sd(E, cs, cv, C, last_col, K, rng=rng)
            sd_log = float(np.std(a, ddof=1))
            mde_log = (Z_ALPHA + Z_POWER) * sd_log / math.sqrt(n_eff)
            mde_pp = 100.0 * abs(math.expm1(-mde_log))
            kill = kill_lines[K]
            ok = mde_pp < kill
            res[K] = (sd_log, mde_pp, kill, ok, len(a))
            tag = "PRIMARY" if K == PRIMARY_WINDOW else "       "
            print(f"  {tag} {K:>2}d | placebo n={len(a):>5} | residual sd "
                  f"{100*sd_log:7.2f} pp(log) | MDE {mde_pp:7.2f} pp | "
                  f"kill line {kill:.1f} pp | {'PASS' if ok else 'FAIL'}")
        v = res[PRIMARY_WINDOW][3]
        print(f"  GATE 2 {'PASS' if v else 'FAIL'}  (PRIMARY {PRIMARY_WINDOW}d window)")
        print()
        return v, res

    ok2, res2 = run_gate2("PRIMARY ARM (clean mid-month stops)", clean, n1, k1)
    ok2b, res2b = run_gate2("ROBUSTNESS ARM (all stops)", stops, n1b, k1b)

    rule()
    print("VERDICT")
    rule()
    if not ok1:
        print(f"  PRIMARY ARM   : KILL_COVERAGE at GATE 1")
        print(f"                  n={n1} (need 40), clusters={k1} (need 20), "
              f"largest cluster {100*share1:.1f}% (max 30%)")
    if not ok2:
        print(f"  PRIMARY ARM   : would ALSO fail GATE 2 POWER "
              f"(MDE {res2[PRIMARY_WINDOW][1]:.2f} pp vs kill line "
              f"{res2[PRIMARY_WINDOW][2]:.1f} pp)")
    if not ok1b:
        print(f"  ROBUSTNESS ARM: fails GATE 1 too "
              f"(n={n1b}, clusters={k1b}, largest {100*share1b:.1f}%)")
    else:
        print(f"  ROBUSTNESS ARM: PASSES GATE 1 (n={n1b}, clusters={k1b}, "
              f"largest {100*share1b:.1f}%)")
    print(f"  ROBUSTNESS ARM: GATE 2 {'PASS' if ok2b else 'FAIL'} "
          f"(MDE {res2b[PRIMARY_WINDOW][1]:.2f} pp vs kill line "
          f"{res2b[PRIMARY_WINDOW][2]:.1f} pp)")
    print()
    if ok1b and ok2b:
        print("  NOTE ON THE ROBUSTNESS ARM: it clears gates 1 and 2 on the declared")
        print("  thresholds, but the pre-registration carried it through GATE 2 ONLY,")
        print("  and gate 3 is not run on it. Two reasons, both fixed in advance:")
        print(f"    (i)  {len(ambiguous)} of its {len(stops)} events "
              f"({100*len(ambiguous)/len(stops):.0f}%) have an event date that is an")
        print("         archive-truncation boundary, not a delisting date -- the outcome")
        print("         window would be mis-anchored by up to 31 days for two thirds of")
        print("         the sample.")
        print("    (ii) per GATE 0 it is not ex-ante tradeable in any case.")
        print("  Extending the protocol to gate 3 after seeing gate 2 pass is exactly")
        print("  the post-hoc move this method exists to prevent. It is not done.")
        print()
    if not (ok1 and ok2):
        print("  GATE 3 IS NOT RUN on the primary arm. No effect number is reported.")
        print()
        economics(res2[PRIMARY_WINDOW][1], None)
        return

    obs, means, lo, hi = gate3("PRIMARY ARM", clean, cs30, cv30, PRIMARY_WINDOW)
    economics(res2[PRIMARY_WINDOW][1], 100.0 * math.expm1(obs.mean()))


if __name__ == "__main__":
    main()
