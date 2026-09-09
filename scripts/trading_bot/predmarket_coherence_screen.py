#!/usr/bin/env python3
"""T47 STANDING DUTY -- mechanical cross-market coherence screen over the FULL predmarket book.

Read-only. Places no bets, freezes nothing, touches no ledger. Input is a file produced by
    python -m scripts.trading_bot.predmarket pull --no-resolve --limit 4000 --criteria-chars 700 > BOOK.json

Three arithmetic tests over CONTEMPORANEOUS prices (no post-cutoff fact needed, so a flag here
escapes the agent's May-2026 knowledge-cutoff disadvantage -- that is the whole point of T47):

  1. DATE-LADDER MONOTONICITY. Questions identical modulo a deadline date. For "by DATE" /
     "before DATE" semantics the event set is NESTED INCREASING, so p must be non-decreasing in
     the date. For "continues through DATE" / "through DATE" semantics it is nested DECREASING,
     so p must be non-increasing. Sign is chosen per-ladder from the wording, not assumed.
  2. WINNER-TAKE-ONE FAMILY SUMS. Markets sharing an event slug that reads as a mutually
     exclusive, exhaustive field: sum(p) should sit near 1.0 (or near k for a k-advance field).
  3. NESTED IMPLICATION on an explicit allow-list of A=>B pairs (p_A must be <= p_B).

Every flag is a CANDIDATE ONLY. T47's rule: both markets' resolution_criteria must be read by a
human/agent before a flag is called an edge -- on Polymarket near-duplicate wording is
load-bearing ("gains" vs "wins" the most seats). The catalogued traps below are suppressed so the
screen does not re-report them every tick.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import defaultdict

# T47 guardrail: known wording traps that LOOK like coherence violations and are not.
CATALOGUED_TRAPS = [
    (re.compile(r"gain the most seats", re.I), "Russia gains-vs-wins: resolves on NET SEAT GAIN vs before the election, not most seats held"),
    (re.compile(r"de facto leader", re.I), "Venezuela de-facto-leader wording differs from the plain leader market"),
    (re.compile(r"finish in (second|third) place", re.I), "Brazil two-advance runoff field sums to 2, not 1"),
    # 2026-09-09: largest apparent cross-venue gap in the book (Poly 3701625 p=0.345 vs Kalshi
    # KXPRESSSECANNOUNCE-26AUG-OCT01 p=0.445, SAME 2026-10-01T03:59Z deadline). Not an edge:
    # Polymarket excludes acting/interim announcements, Kalshi explicitly includes them, so the
    # Kalshi event set strictly contains the Polymarket one and p_kalshi >= p_poly is REQUIRED.
    (re.compile(r"press secretary", re.I), "Press Secretary acting/interim: Kalshi INCLUDES acting/interim, Polymarket EXCLUDES it -- Kalshi's event set strictly contains Polymarket's, so a positive gap is required, not an edge"),
]

# A field is winner-take-one only if EVERY leg reads as "one named contender takes the single
# slot". "which countries will X visit" / "who will X purge" are multi-select and are excluded.
EXCLUSIVE_SHAPE_RE = re.compile(
    r"\b(win|wins|be the next|nominee|nomination|elected|become the|most seats|"
    r"finish in|gain the most|winner)\b", re.I)
MULTISELECT_RE = re.compile(r"^\s*(which|who will .* (purge|leave|be charged|be pardoned))", re.I)

DATE_RE = re.compile(
    r"\b(by|before|through|on)\s+"
    r"(january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s*\d{1,2}(\s*,?\s*\d{4})?|"
    r"\b(by|before|through)\s+(end of\s+)?\d{4}\b|\bby end of \d{4}\b|\b\d{4}\b",
    re.I,
)


def trap_reason(q: str):
    for rx, why in CATALOGUED_TRAPS:
        if rx.search(q or ""):
            return why
    return None


ON_DATE_RE = re.compile(r"\bon\s+(january|february|march|april|may|june|july|august|september|"
                        r"october|november|december)\s*\d{1,2}", re.I)


def ladder_sign(q: str):
    """'up' = p non-decreasing in date (by/before DATE). 'down' = non-increasing. None = not a ladder.

    "Israel military action against Lebanon ON September 8/9" are two SEPARATE single-day
    events, not a nested deadline ladder: P(action on the 9th) carries no implication for
    P(action on the 8th). Treating them as a ladder fired a spurious flag, so an ON-DATE
    question is excluded from the monotonicity test entirely.
    """
    ql = (q or "").lower()
    if ON_DATE_RE.search(ql):
        return None
    if "continues through" in ql or re.search(r"\bthrough\b", ql):
        return "down"
    if re.search(r"\b(by|before)\b", ql):
        return "up"
    return None


def norm_question(q: str) -> str:
    """Collapse ONLY the deadline phrase, keeping every other token including digits.

    An earlier version stripped all non-alphabetic characters, which silently merged
    "Will the Republican Party win the VA-05 House seat?" with "...VA-02...", and
    "Musk posts 200-219 tweets" with "...120-139 tweets" -- so a ladder test fired on
    two genuinely different events. Distinguishing digits are load-bearing; keep them.
    """
    s = DATE_RE.sub(" <DATE> ", (q or "").lower())
    s = re.sub(r"[^a-z0-9<>\-\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_dt(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def screen(book, *, max_days, min_vol, max_spread, lo, hi):
    now = dt.datetime.now(dt.timezone.utc)
    cands = []
    for m in book["markets"]:
        if not m.get("selectable"):
            continue
        c = parse_dt(m.get("close_time"))
        p = m.get("p_market")
        if c is None or p is None:
            continue
        days = (c - now).days
        if not (0 <= days <= max_days):
            continue
        if (m.get("volume") or 0) < min_vol:
            continue
        if (m.get("spread") or 0) > max_spread:
            continue
        if not (lo <= p <= hi):
            continue
        cands.append(dict(m, _days=days, _close=c))

    flags = []
    suppressed = defaultdict(int)

    # --- Test 1: date-ladder monotonicity -------------------------------------------------
    ladders = defaultdict(list)
    for m in cands:
        ladders[(m["venue"], norm_question(m["question"]))].append(m)
    n_ladders = 0
    for key, group in ladders.items():
        if len(group) < 2:
            continue
        n_ladders += 1
        group.sort(key=lambda m: m["_close"])
        sign = ladder_sign(group[0]["question"])
        if sign is None:
            n_ladders -= 1
            continue
        for a, b in zip(group, group[1:]):
            if a["_close"] == b["_close"]:
                continue
            bad = (b["p_market"] < a["p_market"] - 1e-9) if sign == "up" else (b["p_market"] > a["p_market"] + 1e-9)
            if not bad:
                continue
            why = trap_reason(a["question"]) or trap_reason(b["question"])
            if why:
                suppressed[why] += 1
                continue
            flags.append({
                "test": "date_ladder_monotonicity", "sign": sign, "venue": a["venue"],
                "earlier": {"id": a["market_id"], "p": a["p_market"], "close": str(a["close_time"]), "q": a["question"]},
                "later": {"id": b["market_id"], "p": b["p_market"], "close": str(b["close_time"]), "q": b["question"]},
                "violation": round(abs(b["p_market"] - a["p_market"]), 4),
            })

    # --- Test 2: winner-take-one family sums ---------------------------------------------
    # TWO corrections over the first version of this screen, both of which made it useless:
    #  (a) It summed the SCREENED legs. The price/volume/spread filters drop legs, so the sum was
    #      a LOWER BOUND on the family total and every filtered family looked short of 1.0. The
    #      sum must be taken over the FULL unfiltered book.
    #  (b) It treated every shared event slug as a mutually exclusive field. Most are not:
    #      "Which countries will Trump visit in 2026", "Who will Xi purge", "Which Trump admin
    #      officials leave" are MULTI-SELECT -- any number of legs can resolve YES, so sum(p) has
    #      no reason to be 1.0. All 31 flags in the first run were this false positive. Only an
    #      exclusive-shape field is tested now.
    all_by_event = defaultdict(list)
    for m in book["markets"]:
        if m.get("p_market") is not None and m.get("url_ref"):
            all_by_event[(m["venue"], m["url_ref"])].append(m)
    screened_events = {(m["venue"], m["url_ref"]) for m in cands if m.get("url_ref")}
    n_fams = 0
    for key, group in all_by_event.items():
        if key not in screened_events or len(group) < 3:
            continue
        closes = {str(m["close_time"]) for m in group}
        if len(closes) != 1:
            continue  # a multi-deadline group is a ladder, not a field
        if not all(EXCLUSIVE_SHAPE_RE.search(m["question"] or "") for m in group):
            continue  # multi-select "which X will Y" -- sum(p) is not pinned to 1.0
        if any(MULTISELECT_RE.search(m["question"] or "") for m in group):
            continue
        n_fams += 1
        s = sum(m["p_market"] for m in group)
        # THIRD correction: only an OVER-round field is ever actionable. sum(p) < 1 is the normal
        # signature of a field with an unlisted "someone else" leg (Nobel Peace Prize: 20 named
        # legs summing to 0.385; next Romanian PM: 31 legs summing to 0.61), and free data cannot
        # establish that a listed field is exhaustive -- so an under-round sum is uninformative,
        # not an edge. Buying every NO leg only pays when sum(p) exceeds the number of winners.
        if s <= 1.0 + 0.12 and s <= 2.0 + 0.12:
            continue
        if min(abs(s - 1.0), abs(s - 2.0)) <= 0.12:
            continue
        why = next((trap_reason(m["question"]) for m in group if trap_reason(m["question"])), None)
        if why:
            suppressed[why] += 1
            continue
        flags.append({
            "test": "family_sum", "venue": group[0]["venue"], "event": key[1],
            "n_legs": len(group), "sum_p": round(s, 4),
            "legs": sorted(({"id": m["market_id"], "p": m["p_market"], "q": m["question"][:90]} for m in group),
                           key=lambda r: -r["p"])[:12],
        })

    # --- Test 3: explicit nested implications --------------------------------------------
    by_id = {(m["venue"], str(m["market_id"])): m for m in cands}
    NESTED = [
        (("polymarket", "2696746"), ("polymarket", "3128887"),
         "a final US-Iran nuclear deal by Sep 30 would imply the blockade ends by Sep 30"),
    ]
    n_nested = 0
    for a_key, b_key, why in NESTED:
        a, b = by_id.get(a_key), by_id.get(b_key)
        if not a or not b:
            continue
        n_nested += 1
        if a["p_market"] > b["p_market"] + 1e-9:
            flags.append({"test": "nested_implication", "implies": why,
                          "A": {"id": a["market_id"], "p": a["p_market"], "q": a["question"]},
                          "B": {"id": b["market_id"], "p": b["p_market"], "q": b["question"]},
                          "violation": round(a["p_market"] - b["p_market"], 4)})

    return {
        "screened_candidates": len(cands),
        "ladders_tested": n_ladders, "families_tested": n_fams, "nested_pairs_tested": n_nested,
        "n_flags": len(flags),
        "suppressed_catalogued_traps": dict(suppressed),
        "flags": flags,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("book", help="JSON file from `predmarket pull`")
    ap.add_argument("--max-days", type=int, default=120)
    ap.add_argument("--min-vol", type=float, default=20000.0)
    ap.add_argument("--max-spread", type=float, default=0.06)
    ap.add_argument("--lo", type=float, default=0.03)
    ap.add_argument("--hi", type=float, default=0.97)
    a = ap.parse_args(argv)
    book = json.load(open(a.book))
    out = screen(book, max_days=a.max_days, min_vol=a.min_vol,
                 max_spread=a.max_spread, lo=a.lo, hi=a.hi)
    out["book_pulled_utc"] = book.get("pulled_utc")
    out["NOTE"] = ("CANDIDATE FLAGS ONLY. T47 rule: read BOTH markets' resolution_criteria before "
                   "calling any flag an edge. Near-duplicate wording is load-bearing.")
    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
