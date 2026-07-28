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
import sqlite3

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_SENTINEL = "11111111111111111111111111111111"


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


def leakage(rows, label):
    """Actor-level leakage under the frozen `creator ∪ user` grouping key."""
    groups = collections.Counter(actor_groups(rows))
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
    print(f"  decode errors        {one('SELECT COUNT(*) FROM decode_error')}")
    unverified = one("SELECT COUNT(*) FROM slot_scan WHERE status='skipped' AND "
                     "(error IS NULL OR error NOT LIKE '%absence verified by getBlocks%')")
    print(f"  skips NOT verified   {unverified}   <- must be 0; -32009 is ambiguous on its own")
    out["completeness"] = {"blocks": len(blocks), "sampled": len(sampled),
                           "accounted": len(sampled & accounted), "missing": len(missing),
                           "status": status_counts, "skips_unverified": unverified,
                           "decode_errors": one("SELECT COUNT(*) FROM decode_error")}

    print("\n=== cohort ===")
    n = one("SELECT COUNT(*) FROM create_event")
    mints = one("SELECT COUNT(DISTINCT mint) FROM create_event")
    print(f"  CreateEvents         {n:,}")
    print(f"  distinct mints       {mints:,}   (must equal CreateEvents)")
    print(f"  distinct slots       {one('SELECT COUNT(DISTINCT slot) FROM create_event'):,}")
    print(f"  realised n vs ~1,715 expectation: the FRACTION was frozen, not the count")
    out["cohort"] = {"create_events": n, "distinct_mints": mints}

    print("\n=== per-stratum yield (stratification only works if every hour contributed) ===")
    empty = 0
    per_hour = []
    for hour, offset, s, e in blocks:
        c = one(f"SELECT COUNT(*) FROM create_event WHERE slot >= {s} AND slot < {e}")
        per_hour.append({"hour": hour, "offset": offset, "creates": c})
        empty += (c == 0)
        print(f"  h={hour:<2} offset {offset:>2}  creates {c:>5}")
    print(f"  hours contributing 0 members: {empty}")
    out["per_hour"] = per_hour

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
    out["leakage"] = [leakage(allrows, "all"), leakage(tradable, "tradable (Mayhem excluded)")]
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

    verdict = "COMPLETE" if not missing and not unverified else "FAIL"
    print(f"\nCENSUS VERDICT: {verdict}")
    out["verdict"] = verdict
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(out, handle, indent=2, sort_keys=True)
        print(f"wrote {args.json}")
    return 0 if verdict == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
