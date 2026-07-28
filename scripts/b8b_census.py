#!/usr/bin/env python3
"""B8b census — the analysis, written BEFORE the scan finished and before any result was read.

Pre-specifying the queries is the same discipline as freezing the sample. An analysis written after
seeing the data can be shaped by it without anyone intending to: a stratum that looks odd invites an
extra breakdown, a rate that disappoints invites a different denominator. Fixing the questions first
removes that freedom.

Every figure here mirrors `research/B8A_COHORT_CENSUS.md` so the two cohorts are directly
comparable, plus the leakage measures that B8a's audit (`agent_discussion.md` Seq 104/105)
established as load-bearing:

- **`creator ∪ user`, not `creator`** — B8a had `creator != user` on 4 of 242 rows, giving a union
  actor space of 161 rather than 157. The bridge count was zero there, which is exactly what would
  have made the weaker key look sufficient.
- **Members from a repeat actor**, not the surplus beyond one-each. B8a's first census quoted the
  surplus (35.1%) as if it were the exposed share; the real figure was 50.4%. Both are computed
  here and labelled distinctly so the mistake cannot recur.

Read-only. Opens the artifact with `mode=ro`.
"""
import argparse
import collections
import json
import math
import sqlite3

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_SENTINEL = "11111111111111111111111111111111"

EXPECTED_BLOCKS = 24              # one 4-minute block per clock hour (freeze §2)
PRECISION_BAR = 0.005             # ±0.5 pp at p≈1%, 95% — the bar the design was sized against
Z = 1.96


def achieved_precision(n, bar=PRECISION_BAR):
    """What this `n` actually supports — reported, never asserted from the design.

    Owner decision A (`DECISIONS.md`, 2026-07-28): the run completes as frozen and the precision
    achieved is reported alongside the realised `n`. The freeze fixed the sampling *fraction*, so
    `n` was always going to land where it landed; stating the interval it supports is the whole
    content of that decision.
    """
    def half_width(p):
        return Z * math.sqrt(p * (1 - p) / n) if n > 0 else float("inf")

    # Largest p for which the bar still holds, by bisection on the (increasing) half-width.
    low, high = 1e-9, 0.5
    if n > 0 and half_width(low) <= bar:
        for _ in range(200):
            middle = (low + high) / 2
            low, high = (middle, high) if half_width(middle) <= bar else (low, middle)
        max_p = low
    else:
        max_p = 0.0
    return {
        "n": n,
        "half_widths": {"0.01": half_width(0.01), "0.033": half_width(0.033)},
        "max_p_meeting_bar": max_p,
        "max_p": max_p,
        "bar": bar,
        "n_required": math.ceil(Z ** 2 * 0.01 * 0.99 / bar ** 2),
        "meets_bar_at_1pct": half_width(0.01) <= bar,
    }


def actor_groups(rows):
    """Connected components of the `creator ∪ user` graph — the frozen grouping key.

    A row whose `creator` differs from its `user` means one actor operating under two pubkeys, so
    the two must land in the same fold. Grouping by `creator` alone would split them. This is
    union-find over the rows: each row unions its own two pubkeys.
    """
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for creator, user in rows:
        union(creator, user)
    return [find(creator) for creator, _ in rows]


def census_failures(blocks, sampled, missing, unverified, decode_errors,
                    create_events, distinct_mints, zero_observed=()):
    """Every condition the census output labels a "must", enforced.

    The original verdict gated on `missing` and `unverified` only, while printing three further
    requirements as commentary. An empty artifact therefore reported COMPLETE: with no sampled
    blocks there are no sampled slots, so nothing can be missing (Seq 129, F1). Decode errors were
    ignored too, so an artifact could FAIL the scanner and pass the census (F2) — and the census is
    the document a reader quotes.
    """
    failures = []
    if len(blocks) != EXPECTED_BLOCKS:
        failures.append(f"{len(blocks)} sampled blocks, expected {EXPECTED_BLOCKS} hourly strata")
    if not sampled:
        failures.append("zero sampled slots — an empty artifact is not a complete one")
    if missing:
        failures.append(f"{len(missing):,} sampled slots unaccounted for")
    if unverified:
        failures.append(f"{unverified} skipped slots not verified by getBlocks")
    if decode_errors:
        # Matches the scanner, which already FAILs on these. An undecodable CreateEvent breaks
        # exhaustiveness, which is C4 - the rule the whole design rests on.
        failures.append(f"{decode_errors} decode errors — exhaustiveness (C4) is not established")
    if distinct_mints != create_events:
        failures.append(f"{create_events:,} CreateEvents but {distinct_mints:,} distinct mints "
                        f"— duplicate membership")
    if zero_observed:
        # A stratum with zero RETRIEVED slots has no observation power, which is not the same as a
        # stratum that was observed and yielded nothing (that stays a NOTE, per Seq 131). Gated
        # here rather than merely printed, because F1 was exactly the defect of printing a "must"
        # and not enforcing it.
        failures.append(f"strata with zero retrieved slots: {list(zero_observed)} — no observation "
                        f"power in those hours, so the sample is not the stratified one declared")
    return failures


def component_map(rows):
    """`pubkey -> component id` over the rows given. Build this from the FULL cohort.

    Separated from `leakage()` deliberately. The actor graph is a fact about actors, not about
    which rows an analysis happens to look at, so it must be built once over every row and then
    applied to whatever subset is being measured.
    """
    roots = actor_groups(rows)
    mapping = {}
    for (creator, user), root in zip(rows, roots):
        mapping[creator] = root
        mapping[user] = root
    return mapping


def leakage(rows, label, component_of):
    """Actor-level leakage under the frozen `creator ∪ user` grouping key.

    `component_of` MUST come from `component_map(all_rows)` — the full cohort — even when `rows`
    is a subset. It is a required argument rather than an optional one on purpose: the original
    version rebuilt the graph from `rows`, so an identity link proven by an *excluded* row was
    lost, and the tradable population's leakage was under-reported. Constructed case from the
    Seq-129 audit: rows `(A,B)` Mayhem, `(A,A)` and `(B,B)` tradable — A and B are one actor,
    true tradable leakage 100%, reported 0%. Defaulting this argument would let that return
    silently, so there is no default.
    """
    missing = {key for pair in rows for key in pair} - set(component_of)
    if missing:
        raise ValueError(
            f"component_of is missing {len(missing)} pubkey(s) present in rows; it must be built "
            f"from the full cohort via component_map(all_rows), not from this subset")
    groups = collections.Counter(component_of[creator] for creator, _ in rows)
    repeat = {k: v for k, v in groups.items() if v > 1}
    members_from_repeat = sum(repeat.values())
    n = len(rows)
    return {
        "population": label, "n": n,
        # Named `actor_groups`, not `creators` - B8a's census conflated the two and the audit
        # (Seq 104) had to correct a figure that was arithmetically right and answered the wrong
        # question. Both quantities are reported here, labelled distinctly.
        "distinct_actor_groups": len(groups),
        "repeat_actor_groups": len(repeat),
        "members_from_a_repeat_actor": members_from_repeat,
        "share_from_repeat_actor": members_from_repeat / n if n else 0.0,
        "surplus_beyond_one_each": n - len(groups),
        "share_surplus": (n - len(groups)) / n if n else 0.0,
        "largest_actor_group": max(groups.values()) if groups else 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="research/b8b_cohort_433894233_434097833.sqlite")
    parser.add_argument("--json", help="write the census as JSON as well")
    args = parser.parse_args()

    db = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
    q = lambda sql: db.execute(sql).fetchall()
    one = lambda sql: db.execute(sql).fetchone()[0]
    out = {}

    print("=== provenance (the artifact describes itself) ===")
    meta = dict(q("SELECT key, value FROM metadata"))
    for key in sorted(meta):
        print(f"  {key:<28} {meta[key]}")
    out["metadata"] = meta

    print("\n=== completeness — exhaustiveness is the claim everything else rests on ===")
    blocks = q("SELECT hour, offset_minutes, start_slot, end_slot_exclusive FROM sampled_block "
               "ORDER BY hour")
    sampled = set()
    for _, _, s, e in blocks:
        sampled |= set(range(s, e))
    accounted = {r[0] for r in q("SELECT slot FROM slot_scan "
                                 "WHERE status IN ('retrieved','skipped')")}
    missing = sampled - accounted
    status_counts = dict(q("SELECT status, COUNT(*) FROM slot_scan GROUP BY status"))
    print(f"  sampled blocks       {len(blocks)} (must be 24)")
    print(f"  sampled slots        {len(sampled):,}")
    print(f"  accounted            {len(sampled & accounted):,}")
    print(f"  MISSING              {len(missing):,}   <- non-zero means FAIL, not a smaller result")
    print(f"  slot status          {status_counts}")
    decode_errors = one("SELECT COUNT(*) FROM decode_error")
    print(f"  decode errors        {decode_errors}   <- must be 0; the scanner FAILs on these too")
    unverified = one("SELECT COUNT(*) FROM slot_scan WHERE status='skipped' AND "
                     "(error IS NULL OR error NOT LIKE '%absence verified by getBlocks%')")
    print(f"  skips NOT verified   {unverified}   <- must be 0; -32009 is ambiguous on its own")
    out["completeness"] = {"blocks": len(blocks), "sampled": len(sampled),
                           "accounted": len(sampled & accounted), "missing": len(missing),
                           "status": status_counts, "skips_unverified": unverified,
                           "decode_errors": decode_errors}

    print("\n=== cohort ===")
    n = one("SELECT COUNT(*) FROM create_event")
    mints = one("SELECT COUNT(DISTINCT mint) FROM create_event")
    print(f"  CreateEvents         {n:,}")
    print(f"  distinct mints       {mints:,}   (must equal CreateEvents)")
    print(f"  distinct slots       {one('SELECT COUNT(DISTINCT slot) FROM create_event'):,}")
    print(f"  realised n vs ~1,715 expectation: the FRACTION was frozen, not the count")
    out["cohort"] = {"create_events": n, "distinct_mints": mints}

    print("\n=== per-stratum yield (stratification only works if every hour contributed) ===")
    # Two different things look identical in a `creates` column, and only one of them is a fault:
    #   * retrieved slots, zero launches  -> an OBSERVATION. Must not FAIL; failing on it would
    #     conflate "we looked and found nothing" with "we did not look", the distinction B7j went
    #     to trouble to preserve (Seq 131 judgement call, which stands).
    #   * zero retrieved slots            -> NO OBSERVATION POWER in that stratum. That is a fault,
    #     and the previous column could not tell it apart from the case above.
    zero_launch, zero_observed, per_hour = [], [], []
    for hour, offset, s, e in blocks:
        created = one(f"SELECT COUNT(*) FROM create_event WHERE slot >= {s} AND slot < {e}")
        retrieved = one(f"SELECT COUNT(*) FROM slot_scan WHERE status = 'retrieved' "
                        f"AND slot >= {s} AND slot < {e}")
        skipped = one(f"SELECT COUNT(*) FROM slot_scan WHERE status = 'skipped' "
                      f"AND slot >= {s} AND slot < {e}")
        per_hour.append({"hour": hour, "offset": offset, "creates": created,
                         "retrieved_slots": retrieved, "skipped_slots": skipped})
        if retrieved == 0:
            zero_observed.append(hour)
        elif created == 0:
            zero_launch.append(hour)
        print(f"  h={hour:<2} offset {offset:>2}  creates {created:>5}   "
              f"retrieved {retrieved:>4}  skipped {skipped:>3}")
    print(f"  strata with retrieved slots but 0 launches: {zero_launch or 'none'}   "
          f"(NOTE, not a fault - we looked and found nothing)")
    print(f"  strata with ZERO retrieved slots:           {zero_observed or 'none'}   "
          f"(FAULT - no observation power in that hour)")
    out["per_hour"] = per_hour
    out["strata_zero_launch"] = zero_launch
    out["strata_zero_observed"] = zero_observed

    print("\n=== quote regime (never pooled; sol_amount must branch on this) ===")
    regimes = q("SELECT quote_mint, COUNT(*) FROM create_event GROUP BY 1 ORDER BY 2 DESC")
    for mint, count in regimes:
        name = "SOL sentinel" if mint == SOL_SENTINEL else ("USDC" if mint == USDC else "OTHER")
        print(f"  {name:<14} {mint:<46} {count:>6}  ({count/n:.2%})" if n else "")
    out["quote_regimes"] = {m: c for m, c in regimes}

    print("\n=== Mayhem (a covariate, excluded at decision time - never a sampling step) ===")
    for column in ("is_mayhem_mode", "is_cashback_enabled"):
        counts = dict(q(f"SELECT {column}, COUNT(*) FROM create_event GROUP BY 1"))
        print(f"  {column:<22} {counts}")
        out[column] = counts

    print("\n=== leakage under the frozen `creator ∪ user` key ===")
    allrows = q("SELECT creator, user FROM create_event")
    tradable = q("SELECT creator, user FROM create_event WHERE is_mayhem_mode = 0")
    creators = {c for c, _ in allrows}
    users = {u for _, u in allrows}
    bridges = [(c, u) for c, u in allrows if c != u and u in creators]
    # Built ONCE over the full cohort, then applied to the tradable subset. Rebuilding it from the
    # subset would drop identity links proven by excluded Mayhem rows and under-report leakage.
    component_of = component_map(allrows)
    out["leakage"] = [leakage(allrows, "all", component_of),
                      leakage(tradable, "tradable (Mayhem excluded)", component_of)]
    for row in out["leakage"]:
        print(f"  {row['population']:<28} n={row['n']:<5} "
              f"actor_groups={row['distinct_actor_groups']:<5} "
              f"repeat={row['repeat_actor_groups']:<4} "
              f"from-repeat={row['members_from_a_repeat_actor']} "
              f"({row['share_from_repeat_actor']:.1%})  surplus={row['share_surplus']:.1%}  "
              f"max={row['largest_actor_group']}")
    print(f"  creator != user rows          {sum(1 for c, u in allrows if c != u)}")
    print(f"  rows bridging two actors      {len(bridges)}  <- non-zero means `creator` alone is "
          f"NOT sufficient")
    print(f"  union actor space             {len(creators | users)}  (creators alone: {len(creators)})")
    out["actor_space"] = {"creators": len(creators), "users": len(users),
                          "union": len(creators | users), "bridges": len(bridges)}

    print("\n=== achieved precision (owner decision A: report it; claim nothing tighter) ===")
    # The freeze fixed the sampling FRACTION, not a target count, and pre-committed to reporting
    # whatever `n` resulted. So the honest output is the interval this `n` actually supports -
    # not silence, and not a bar asserted from the design.
    precision = achieved_precision(n)
    for p, half in sorted(precision["half_widths"].items()):
        verdict_mark = "meets" if half <= PRECISION_BAR else "MISSES"
        print(f"  p={float(p):>5.1%}   95% half-width ±{half*100:.3f} pp   {verdict_mark} the "
              f"±{PRECISION_BAR*100:.1f} pp design bar")
    print(f"  the ±{PRECISION_BAR*100:.1f} pp bar holds for every p ≤ {precision['max_p']:.2%}")
    print(f"  n required for ±{PRECISION_BAR*100:.1f} pp at p=1%: {precision['n_required']:,} "
          f"(realised {n:,})")
    out["precision"] = precision

    failures = census_failures(blocks=blocks, sampled=sampled, missing=missing,
                               unverified=unverified, decode_errors=decode_errors,
                               create_events=n, distinct_mints=mints,
                               zero_observed=zero_observed)
    if zero_launch:
        # Deliberately NOT a failure. A 4-minute block genuinely containing no launch is an
        # observation, and treating it as a fault would conflate "we did not look" with "we looked
        # and found nothing" - the distinction B7j went to some trouble to preserve.
        print(f"  NOTE: {len(zero_launch)} hourly strata were observed and contributed no members "
              f"({zero_launch}). Not a failure; reported because a stratum yielding nothing still "
              f"weighs in any per-hour comparison.")

    verdict = "FAIL" if failures else "COMPLETE"
    print(f"\nCENSUS VERDICT: {verdict}")
    for reason in failures:
        print(f"  FAIL: {reason}")
    out["verdict"] = verdict
    out["failures"] = failures
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(out, handle, indent=2, sort_keys=True)
        print(f"wrote {args.json}")
    return 0 if verdict == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
