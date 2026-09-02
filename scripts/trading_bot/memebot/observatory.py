#!/usr/bin/env python3
"""Launchpad Observatory — the dashboard state assembler.

WHAT THIS IS
------------
One read-only function, `build_state()`, that assembles everything the launchpad observatory dashboard
renders. It owns NO economics of its own: every constant comes from `venues.py` (the frozen, measured
registry) or from a file on disk that was written by a measurement. Where a venue refuses to produce a
number, this module carries the REFUSAL TEXT forward instead of substituting a guess — a dashboard that
prints an invented multiple is worse than one that prints an em-dash.

THE FIVE SECTIONS
-----------------
1. VENUE ECONOMICS — one row per registry venue: X, toll, p, break-even premium m*, EV at the floor,
   and the prize term (X-1)p. Every field is `venues.py`'s, never recomputed here.
2. THE EV CURVE     — EV(m) = (1 + (X-1)p)/m - 1 - toll sampled on m in [1.00, 2.00] per venue, plus the
   break-even crossing m*. This is the centrepiece: the curve crosses zero and stays negative, and every
   venue crosses at almost the same place.
3. LAUNCHLAB CENSUS — the 1,292,348-curve status census read off the FREE public RPC, plus an optional,
   bounded `refresh_census()` that re-runs it. Refresh NEVER runs inside build_state().
4. LIVE TAPE        — whatever the multi-venue collector has actually taped. Zero rows reports zero rows.
5. LABEL LEDGER     — the headline: 82 b11a labels vs 13,694 LaunchLab labels, and the floor-cohort
   positive count that the label wall was blocking.

WHY THE EV FRAME IS THE WHOLE STORY
-----------------------------------
`research/b11a` established that a pump.fun-style bonding curve is HARD-FLOORED at its launch price —
0 of 3,239 curves ever traded below their first observed price. So on-curve downside is bounded by the
premium you paid above the floor, and the only upside that is not a market forecast is the deterministic
graduation multiple X, which is a fixed point of the curve rather than an outcome. That collapses the
entire venue-selection question to one line of algebra, which is what this dashboard draws.

READ-ONLY. Zero writes except the census JSON, and only when `refresh_census()` is called explicitly.
Never touches the live pump tape. Never touches any arena closure file.

    python -m scripts.trading_bot.memebot.observatory              # print state as JSON
    python -m scripts.trading_bot.memebot.observatory --refresh    # re-measure the census first
"""
from __future__ import annotations

import base64
import datetime as _dt
import json
import pathlib
import time
import urllib.error
import urllib.request

from . import venues as V
from . import multivenue_tape as MVT

SCHEMA_VERSION = 1

_ROOT = pathlib.Path(__file__).resolve().parents[3]
CENSUS_PATH = _ROOT / "research" / "launchpads" / "census" / "launchlab_census.json"
CONSTANTS_PATH = _ROOT / "research" / "launchpads" / "MEASURED_CONSTANTS.json"

# The FREE public endpoint. Helius is 429 "max usage reached" — everything here must work without it.
FREE_RPC = "https://api.mainnet-beta.solana.com"

# Measured layout constants for the LaunchLab PoolState account (research/launchpads/MEASURED_CONSTANTS).
# The discriminator is re-derived from the pinned on-chain IDL at call time rather than hardcoded, so an
# IDL swap refuses loudly instead of silently counting the wrong accounts.
POOLSTATE_STATUS_OFFSET = 17
POOLSTATE_STATUS_CODES = {0: "funding", 1: "awaiting_migration", 2: "migrated"}

# The b11a label wall, quoted from venues.py's own module docstring so the two can never drift apart.
B11A_CURVES_OBSERVED = 3239        # curves with a price history; 0 ever traded below their first price
B11A_CREATE_COHORT = 3932          # survivorship-free 23h create window
B11A_GRADUATIONS = 82              # the entire pump.fun label set
B11A_FLOOR_COHORT = 2975           # curves that were still AT the floor when a buyer could act
B11A_FLOOR_COHORT_POSITIVES = 3    # ...of which THREE graduated. That is the wall.

# EV curve sampling. m = entry price / floor price; 1.00 is the floor itself, 2.00 is "paid double".
EV_CURVE_M_MIN = 1.00
EV_CURVE_M_MAX = 2.00
EV_CURVE_STEPS = 100


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _round(x, nd=6):
    return None if x is None else round(float(x), nd)


# ---------------------------------------------------------------------------------------------------
# 1. VENUE ECONOMICS
# ---------------------------------------------------------------------------------------------------
def _refusal(fn, *args, **kwargs):
    """Call a venues.py accessor; return (value, None) or (None, the refusal text it raised).

    This is the honesty seam of the whole dashboard. venues.py raises VenueRefused for Boop's multiple
    (damping_term=31 makes the curve non-CP and the two plain-CP readings disagree, 15.15x vs 23.36x)
    and for Heaven (no curve exists at all). Those refusals are CONTENT, not errors: the dashboard shows
    the reason a cell is an em-dash.
    """
    try:
        return fn(*args, **kwargs), None
    except V.VenueRefused as exc:
        return None, str(exc)


def venue_economics() -> list[dict]:
    """One row per registry venue. Every economic number is venues.py's; none is recomputed here."""
    rows = []
    for vid, v in V.VENUES.items():
        x, x_refusal = _refusal(V.graduation_multiple, v)
        m_star = ev_floor = prize = None
        m_star_refusal = None
        if x is not None and v.graduation_rate_p is not None:
            m_star, m_star_refusal = _refusal(V.ev_breakeven_premium, v, v.graduation_rate_p)
            ev_floor, _ = _refusal(V.ev_at_premium, v, v.graduation_rate_p, 1.0)
            prize, _ = _refusal(V.prize_term, v)
        elif x is not None and v.graduation_rate_p is None:
            m_star_refusal = f"{vid}: graduation rate p is NOT established. {v.unverified or ''}".strip()

        rows.append({
            "venue_id": vid,
            "display_name": v.display_name,
            "chain": v.chain,
            "program_id": v.program_id,
            "platform_config": v.platform_config,
            "quote_symbol": v.quote_symbol,
            "curve_kind": v.curve_kind,
            "verified_onchain": v.verified_onchain,
            "graduation_multiple_x": _round(x),
            "graduation_multiple_refusal": x_refusal,
            "toll_per_side": v.toll_per_side,
            "toll_round_trip": v.toll_round_trip,
            "graduation_rate_p": _round(v.graduation_rate_p, 8),
            "p_n": v.p_n,
            "p_grads": v.p_grads,
            "p_basis": v.p_basis,
            "breakeven_premium_m_star": _round(m_star),
            "breakeven_refusal": m_star_refusal,
            "ev_at_floor_m_1": _round(ev_floor),
            "prize_term_Xm1p": _round(prize),
            # rank_caveats() reads p_n / p_grads, which are None on a venue whose p was never
            # established — it would render "census n=None < 1000" and "only None graduations".
            # A venue with no p has no rank to caveat: the refusal IS the finding.
            "caveats": V.rank_caveats(v) if v.graduation_rate_p is not None else [],
            "tradeable": x is not None and v.graduation_rate_p is not None
                         and v.toll_round_trip is not None,
            "provenance": v.provenance,
            "unverified": v.unverified,
            "note": v.note,
        })
    # Rank order is venues.py's own: break-even premium descending, refusing venues last.
    ranked = {r["venue_id"]: i for i, r in enumerate(V.rank_venues())}
    rows.sort(key=lambda r: (ranked.get(r["venue_id"], 10_000), r["venue_id"]))
    return rows


# ---------------------------------------------------------------------------------------------------
# 2. THE EV CURVE
# ---------------------------------------------------------------------------------------------------
def ev_curves(m_min: float = EV_CURVE_M_MIN, m_max: float = EV_CURVE_M_MAX,
              steps: int = EV_CURVE_STEPS) -> dict:
    """EV(m) sampled per venue over the entry-premium range, for the centrepiece graph.

    Each series is the venue's OWN measured p and toll pushed through venues.ev_at_premium — the
    dashboard draws exactly the algebra the registry defines, with no interpolation of its own.
    """
    series = []
    for vid, v in V.VENUES.items():
        if v.graduation_multiple_x is None or v.graduation_rate_p is None or v.toll_round_trip is None:
            continue
        points = []
        for i in range(steps + 1):
            m = m_min + (m_max - m_min) * i / steps
            points.append([round(m, 4), _round(V.ev_at_premium(v, v.graduation_rate_p, m))])
        series.append({
            "venue_id": vid,
            "display_name": v.display_name,
            "X": _round(v.graduation_multiple_x),
            "p": _round(v.graduation_rate_p, 8),
            "toll_round_trip": v.toll_round_trip,
            "breakeven_premium_m_star": _round(V.ev_breakeven_premium(v, v.graduation_rate_p)),
            "ev_at_floor_m_1": _round(V.ev_at_premium(v, v.graduation_rate_p, 1.0)),
            "prize_term_Xm1p": _round(V.prize_term(v)),
            "caveats": V.rank_caveats(v),
            "points": points,
        })
    series.sort(key=lambda s: s["breakeven_premium_m_star"], reverse=True)

    credible = [s for s in series if not s["caveats"]]
    prize_terms = [s["prize_term_Xm1p"] for s in credible]
    return {
        "formula_ev": "EV(m) = (1 + (X-1)p)/m - 1 - toll",
        "formula_breakeven": "m* = (1 + (X-1)p) / (1 + toll)",
        "m_min": m_min, "m_max": m_max, "steps": steps,
        "x_axis": "entry premium m = entry price / floor (launch) price",
        "y_axis": "expected return per round trip, decimal",
        "series": series,
        "credible_venue_ids": [s["venue_id"] for s in credible],
        # The collapse: X spans 11x..200x and p spans 0.045%..2.09%, yet the product that is the ENTIRE
        # upside of the frame lands in a narrow band. Launchpads compete on curve shape; the market
        # prices it straight back out. This is the efficiency result, and it belongs on the graph.
        "prize_term_band": {
            "min": min(prize_terms) if prize_terms else None,
            "max": max(prize_terms) if prize_terms else None,
            "n_credible": len(credible),
            "note": "(X-1)p across every venue whose census is large enough to believe. X spans an "
                    "order of magnitude; the prize term does not. The prize and the base rate cancel.",
        },
    }


# ---------------------------------------------------------------------------------------------------
# 3. LAUNCHLAB CENSUS  (read from disk; optional bounded re-measurement off the FREE public RPC)
# ---------------------------------------------------------------------------------------------------
def _poolstate_discriminator_b64() -> str:
    """PoolState's 8-byte Anchor discriminator, re-derived from the PINNED on-chain IDL.

    venues.verify_pinned_idls() is called first so a drifted IDL refuses rather than quietly filtering
    on a stale discriminator and returning a plausible-but-wrong census.
    """
    V.verify_pinned_idls()
    fname, _ = V.PINNED_IDLS["raydium_launchlab"]
    idl = json.loads((V.IDL_DIR / fname).read_bytes())
    for acct in idl.get("accounts", []):
        if acct["name"] == "PoolState":
            return base64.b64encode(bytes(acct["discriminator"])).decode()
    raise V.VenueRefused("raydium_launchlab IDL has no PoolState account — refusing to census")


def _census_elapsed_s(census: dict) -> str:
    """How long the census on disk actually took, from its own record.

    This used to be the literal string "37 seconds" — true of one run, and wrong the moment the census
    was re-measured (a later run took 26.4s). The census writes its own per-stage timings; read them.
    """
    stages = census.get("elapsed_seconds") if census.get("available") else None
    if isinstance(stages, dict):
        total = sum(v for v in stages.values() if isinstance(v, (int, float)))
        if total:
            return f"{total:.0f} seconds"
    if isinstance(stages, (int, float)) and stages:
        return f"{stages:.0f} seconds"
    return "under a minute"


def read_census(path: pathlib.Path = CENSUS_PATH) -> dict:
    """The census as last measured. Missing file is reported as missing, never as zeroes."""
    try:
        body = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"available": False, "path": str(path), "error": str(exc)}
    body["available"] = True
    body["path"] = str(path)
    counts = body.get("counts") or {}
    total = body.get("total_curves")

    def _share(key):
        # Guard the NUMERATOR as well as the denominator. A census that is valid JSON but missing a
        # status key (a hand edit, or a half-written file) must render an em-dash, not take the whole
        # dashboard down with a TypeError. "Missing is reported as missing" applies to fields too.
        n = counts.get(key)
        if not isinstance(n, (int, float)) or not isinstance(total, (int, float)) or not total:
            return None
        return n / total

    body["derived"] = {
        "status_labels": POOLSTATE_STATUS_CODES,
        "funding_share": _share("funding"),
        "migrated_share": _share("migrated"),
        # The status byte lives in an account that is never closed, so a graduation label is PERMANENT
        # and the census is survivorship-free by construction — unlike a create-window sample, which
        # can only see the coins that were alive when it looked.
        "survivorship": "PoolState accounts are never closed: status@17 is a permanent, "
                        "survivorship-free graduation label for every curve ever opened.",
    }
    return body


def refresh_census(rpc_url: str = FREE_RPC, *, path: pathlib.Path = CENSUS_PATH,
                   timeout_s: float = 180.0, write: bool = True) -> dict:
    """Re-run the three status counts against the FREE public RPC and rewrite the census JSON.

    Three `getProgramAccounts` calls, each filtered by memcmp(PoolState discriminator @0) AND
    memcmp(status byte @17), with `dataSlice {offset:0,length:0}` so the node returns account KEYS ONLY
    and never megabytes of account data. That dataSlice is what makes a 1.29-million-account census
    finish in ~37s on a free endpoint at $0.

    BOUNDED AND OPTIONAL: build_state() never calls this. It is a button, not a dependency — a slow or
    rate-limited public RPC must degrade the refresh, not the dashboard.
    """
    disc_b64 = _poolstate_discriminator_b64()
    program = V.LAUNCHLAB_PROGRAM
    started = time.time()
    counts: dict[str, int] = {}
    elapsed: dict[str, float] = {}

    for code, name in sorted(POOLSTATE_STATUS_CODES.items()):
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "getProgramAccounts",
            "params": [program, {
                "encoding": "base64",
                "dataSlice": {"offset": 0, "length": 0},
                "filters": [
                    {"memcmp": {"offset": 0, "bytes": disc_b64, "encoding": "base64"}},
                    {"memcmp": {"offset": POOLSTATE_STATUS_OFFSET,
                                "bytes": base64.b64encode(bytes([code])).decode(),
                                "encoding": "base64"}},
                ],
            }],
        }
        t0 = time.time()
        request = urllib.request.Request(
            rpc_url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as handle:
                body = json.loads(handle.read())
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "stage": name, "error": f"{type(exc).__name__}: {exc}",
                    "rpc": rpc_url, "elapsed_seconds": round(time.time() - started, 1)}
        if "error" in body:
            return {"ok": False, "stage": name, "error": json.dumps(body["error"])[:400],
                    "rpc": rpc_url, "elapsed_seconds": round(time.time() - started, 1)}
        counts[name] = len(body.get("result") or [])
        elapsed[name] = round(time.time() - t0, 1)

    total = sum(counts.values())
    graduated = counts.get("migrated", 0)
    if total <= 0:
        return {"ok": False, "stage": "total", "error": "census returned zero accounts — refusing to "
                "overwrite a good measurement with an empty one", "rpc": rpc_url}

    previous = read_census(path)
    record = {
        "schema": 1,
        "measured_utc": _now_iso(),
        "source": f"{rpc_url} (free public RPC)",
        "method": (f"getProgramAccounts dataSlice0 + memcmp(PoolState disc@0, "
                   f"status@{POOLSTATE_STATUS_OFFSET})"),
        "program": program,
        "counts": counts,
        "total_curves": total,
        "graduations": graduated,
        "graduation_rate_p": graduated / total,
        "labels_vs_b11a": {
            "b11a_labels": B11A_GRADUATIONS,
            "launchlab_labels": graduated,
            "multiple": round(graduated / B11A_GRADUATIONS, 1),
        },
        "cross_check": previous.get("cross_check") if previous.get("available") else None,
        "elapsed_seconds": elapsed,
        "cost_usd": 0.0,
    }
    if previous.get("available") and previous.get("graduation_rate_p"):
        record["cross_check"] = {
            "previous_measured_utc": previous.get("measured_utc"),
            "previous_p": previous.get("graduation_rate_p"),
            "measured_p": record["graduation_rate_p"],
            "delta_p": record["graduation_rate_p"] - previous["graduation_rate_p"],
            # NOT the previous file's note. That note described the ORIGINAL comparison against a
            # separately-transcribed recon value; pasting it onto a measurement-vs-measurement delta
            # would assert a check this record never performed. Say what THIS record compared.
            "note": "measurement-vs-measurement: this census against the one it replaced. "
                    "Drift is expected and small — new curves open continuously.",
        }
        # The genuinely independent anchor (a separate pipeline's transcribed p) is worth keeping, but
        # only under its own key, with its own delta, so it can never be mistaken for the delta above.
        prev_cc = previous.get("cross_check")
        anchor = prev_cc.get("recon_transcribed_p") if isinstance(prev_cc, dict) else None
        if isinstance(anchor, (int, float)):
            record["cross_check"]["recon_transcribed_p"] = anchor
            record["cross_check"]["delta_vs_recon"] = record["graduation_rate_p"] - anchor
            # Do NOT assert agreement unconditionally — that is the same defect as pasting the old
            # note forward. Compare, then state the result of the comparison.
            rel = abs(record["graduation_rate_p"] - anchor) / anchor if anchor else None
            record["cross_check"]["recon_relative_delta"] = rel
            record["cross_check"]["recon_note"] = (
                "independent confirmation: an unrelated pipeline transcribed p="
                f"{anchor:.6g}; this measurement agrees to within {rel:.2%}."
                if rel is not None and rel <= 0.01 else
                "DISAGREEMENT: an unrelated pipeline transcribed p="
                f"{anchor:.6g}, but this measurement reads "
                f"{record['graduation_rate_p']:.6g}"
                + (f" ({rel:.1%} apart)" if rel is not None else "")
                + " — one of the two is measuring a different population.")
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2) + "\n")
    return {"ok": True, "written": bool(write), "path": str(path),
            "elapsed_seconds": round(time.time() - started, 1), "census": record}


# ---------------------------------------------------------------------------------------------------
# 4. LIVE TAPE
# ---------------------------------------------------------------------------------------------------
def _tail_rows(tape: MVT.MultiVenueTape, max_bytes: int = 2_000_000) -> list[dict]:
    """Parse the last `max_bytes` of the tape into rows, dropping a leading partial line.

    Bounded so a multi-hundred-megabyte tape cannot make a dashboard request hang. Read-only: it opens
    the collector's OWN tape ('rb'), never the live pump tape, and never takes the writer lock.
    """
    if not tape.path.exists():
        return []
    size = tape.path.stat().st_size
    with tape.path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(size - max_bytes)
            handle.readline()                 # discard the partial first line
        buf = handle.read()
    rows = []
    for chunk in buf.split(b"\n"):
        if not chunk.strip():
            continue
        try:
            rows.append(json.loads(chunk))
        except json.JSONDecodeError:
            continue                          # a write in flight; the next pass will see it whole
    return rows


def live_tape(*, recent: int = 40) -> dict:
    """What the multi-venue collector has ACTUALLY taped. Zero rows reports zero rows."""
    tape = MVT.MultiVenueTape()
    out: dict = {"tape_path": str(tape.path), "exists": tape.path.exists()}
    try:
        summary = MVT.report(tape)
    except MVT.Refused as exc:
        # A broken hash chain is a hard finding, not a blank panel.
        return {**out, "chain_verified": False, "rows": None, "refused": str(exc),
                "recent_creates": [], "recent_graduations": [], "per_venue": {},
                "health": MVT.stream_health()}
    out.update({
        "chain_verified": summary.get("chain_verified"),
        "rows": summary.get("rows", 0),
        "head_sha256": summary.get("head_sha256"),
        "bytes": summary.get("bytes", 0),
        "per_venue": summary.get("per_venue", {}),
        "graduations_matched_to_a_taped_create": summary.get("graduations_matched_to_a_taped_create", {}),
        "first_unix_nanos": summary.get("first_unix_nanos"),
        "last_unix_nanos": summary.get("last_unix_nanos"),
        "span_hours": summary.get("span_hours"),
        "health": summary.get("health"),
    })

    creates, grads = [], []
    if out["rows"]:
        for row in _tail_rows(tape):
            ns = row.get("received_unix_nanos")
            item = {
                "venue": row.get("venue"),
                "kind": row.get("kind"),
                "mint": row.get("mint") or row.get("base_mint"),
                "pool_id": row.get("pool_id"),
                "name": row.get("name"),
                "symbol": row.get("symbol"),
                "signature": row.get("signature"),
                "slot": row.get("slot"),
                "received_unix_nanos": ns,
                "received_utc": (_dt.datetime.fromtimestamp(ns / 1e9, _dt.timezone.utc)
                                 .strftime("%Y-%m-%dT%H:%M:%SZ")) if isinstance(ns, int) else None,
                "sequence": row.get("sequence"),
            }
            (grads if row.get("kind") == "graduation" else creates).append(item)
    out["recent_creates"] = creates[-recent:][::-1]
    out["recent_graduations"] = grads[-recent:][::-1]
    out["recent_window_note"] = ("recent rows are read from the tail of the tape (bounded read); "
                                 "per_venue counts are over the WHOLE verified chain")
    if not out["rows"]:
        # Report the collector's OWN health rather than asserting a cause. An earlier version of this
        # string blamed Helius rate-limiting; that stopped being true once the collector was pointed at
        # the free public RPC, and a dashboard that explains an empty panel with a stale guess is
        # exactly the failure this module exists to avoid.
        health = out.get("health") or {}
        reason = health.get("reason") or health.get("status")
        out["empty_reason"] = (
            "no rows taped yet — the collector reports: "
            + (str(reason) if reason else "no collector has run against this tape")
            + ". The census and the registry do not depend on it; this panel stays empty rather "
              "than inventing rows. Start one with: python -m "
              "scripts.trading_bot.memebot.multivenue_tape --programs pump.fun,raydium_launchlab")
    return out


# ---------------------------------------------------------------------------------------------------
# 5. LABEL LEDGER
# ---------------------------------------------------------------------------------------------------
def label_ledger(census: dict | None = None) -> dict:
    """The headline comparison: what the label wall was, and what the census just unlocked.

    b11a could measure the floor cohort's graduation rate off THREE positives. A rate estimated from
    three events has a 95% Poisson interval spanning roughly an order of magnitude, which is why the
    provenance test could not run: any effect smaller than 'enormous' was invisible. LaunchLab's status
    byte is the same label on the same curve geometry, at 167x the count.
    """
    census = census if census is not None else read_census()
    ll_labels = census.get("graduations") if census.get("available") else None
    ll_total = census.get("total_curves") if census.get("available") else None

    pump = V.VENUES["pump.fun"]
    bonk = V.VENUES["letsbonk"]
    return {
        "b11a": {
            "source": "research/b11a — survivorship-free 23h pump.fun create window, 11.9d follow",
            "creates": B11A_CREATE_COHORT,
            "graduations": B11A_GRADUATIONS,
            "graduation_rate_p": _round(pump.graduation_rate_p, 8),
            "curves_with_price_history": B11A_CURVES_OBSERVED,
            "curves_that_traded_below_launch_price": 0,
            "floor_cohort": B11A_FLOOR_COHORT,
            "floor_cohort_positives": B11A_FLOOR_COHORT_POSITIVES,
            "wall": (f"{B11A_FLOOR_COHORT_POSITIVES} positives in a floor cohort of "
                     f"{B11A_FLOOR_COHORT}. Every conditional test — does the creator's history "
                     "predict graduation? does the first-minute flow? — divides by three."),
        },
        "launchlab": {
            "source": census.get("source") if census.get("available") else None,
            "measured_utc": census.get("measured_utc") if census.get("available") else None,
            "curves": ll_total,
            "graduations": ll_labels,
            "graduation_rate_p": _round(census.get("graduation_rate_p"), 8)
                                 if census.get("available") else None,
            "cost_usd": census.get("cost_usd") if census.get("available") else None,
            "why_comparable": (
                "Same curve geometry as pump.fun by measurement, not by assumption: "
                f"Q0={bonk.q0_quote} SOL, R={bonk.raise_quote} SOL -> X={_round(bonk.graduation_multiple_x, 4)} "
                f"against pump.fun's Q0={pump.q0_quote}, R={pump.raise_quote} -> "
                f"X={_round(pump.graduation_multiple_x, 4)}. Different toll "
                f"({bonk.toll_round_trip:.1%} vs {pump.toll_round_trip:.1%}) and half the graduation "
                "rate, which makes it a natural control rather than merely more data."),
        },
        "multiple": round(ll_labels / B11A_GRADUATIONS, 1) if ll_labels else None,
        "unlocks": [u for u in [
            f"Graduation labels go from {B11A_GRADUATIONS} to {ll_labels:,} "
            f"({round(ll_labels / B11A_GRADUATIONS, 1)}x)." if ll_labels else None,
            "The floor cohort's positive count is no longer 3: LaunchLab's status byte is a permanent, "
            "survivorship-free label on every curve ever opened, so a floor-priced cohort can be cut "
            "from a population that already contains its own outcomes.",
            "Provenance and first-flow tests that were underpowered at n=3 become testable, on a venue "
            "whose curve is the same shape and whose toll and base rate are both measured.",
            "Cost of the whole label set: $0 on the free public RPC in "
            f"{_census_elapsed_s(census)}.",
        ] if u],
    }


# ---------------------------------------------------------------------------------------------------
# THE ASSEMBLER
# ---------------------------------------------------------------------------------------------------
def build_state(*, recent: int = 40) -> dict:
    """Everything the observatory renders, in one read-only pass. Never performs a network call."""
    census = read_census()
    econ = venue_economics()
    curves = ev_curves()
    tape = live_tape(recent=recent)
    ledger = label_ledger(census)

    tradeable = [r for r in econ if r["tradeable"]]
    refusing = [r for r in econ if r["graduation_multiple_refusal"]]
    credible = V.rank_venues(credible_only=True)
    pump = V.VENUES["pump.fun"]

    try:
        idls = V.verify_pinned_idls()
        idl_status = "verified"
    except (V.VenueRefused, OSError) as exc:
        idls, idl_status = {}, f"REFUSED: {exc}"

    return {
        "schema": SCHEMA_VERSION,
        "generated_utc": _now_iso(),
        "title": "Launchpad Observatory",
        "subtitle": "measured launch-curve economics across every Solana launchpad",
        "kpis": {
            "venues_in_registry": len(econ),
            "venues_verified_onchain": sum(1 for r in econ if r["verified_onchain"]),
            "venues_with_full_economics": len(tradeable),
            "venues_refusing_a_multiple": len(refusing),
            "credible_ranks": len(credible),
            "launchlab_curves": census.get("total_curves") if census.get("available") else None,
            "launchlab_graduations": census.get("graduations") if census.get("available") else None,
            "launchlab_p": _round(census.get("graduation_rate_p"), 8)
                           if census.get("available") else None,
            "label_multiple_vs_b11a": ledger.get("multiple"),
            "pumpfun_breakeven_m_star": _round(
                V.ev_breakeven_premium(pump, pump.graduation_rate_p)),
            "pumpfun_ev_at_floor": _round(V.ev_at_premium(pump, pump.graduation_rate_p, 1.0)),
            "prize_term_band": curves["prize_term_band"],
            "tape_rows": tape.get("rows"),
            "census_cost_usd": census.get("cost_usd") if census.get("available") else None,
        },
        "venues": econ,
        "ev_curves": curves,
        "census": census,
        "tape": tape,
        "label_ledger": ledger,
        "ranked": V.rank_venues(),
        "not_on_solana": V.NOT_ON_SOLANA,
        "toll_discrepancy": V.TOLL_DISCREPANCY,
        "provenance": {
            "registry_sha256": V.registry_sha256(),
            "registry_schema": V.SCHEMA_VERSION,
            "pinned_idls": idls,
            "pinned_idl_status": idl_status,
            "census_path": str(CENSUS_PATH),
            "constants_path": str(CONSTANTS_PATH),
            "tape_path": str(MVT.TAPE_PATH),
            "free_rpc": FREE_RPC,
            "law": "X = (Q0 + R)^2 / Q0^2 for a constant-product curve; "
                   "X = (migration_sqrt/sqrt_start)^2 for Meteora DBC's piecewise-CL curve",
            "floor_result": (f"0 of {B11A_CURVES_OBSERVED} pump.fun curves ever traded below their "
                             "first observed price — the curve is hard-floored at launch, which is "
                             "what makes the entry premium m the entire downside."),
        },
        "footer": (f"registry {V.registry_sha256()[:12]} · census "
                   f"{census.get('measured_utc') if census.get('available') else 'MISSING'} · "
                   f"tape {tape.get('rows')} rows · read-only · $0 free-RPC"),
    }


def _main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true",
                    help="re-measure the LaunchLab census off the free public RPC before printing")
    ap.add_argument("--rpc", default=FREE_RPC)
    ap.add_argument("--no-write", action="store_true", help="refresh but do not rewrite the census JSON")
    ap.add_argument("--compact", action="store_true", help="drop EV curve point arrays from the output")
    args = ap.parse_args()

    if args.refresh:
        result = refresh_census(args.rpc, write=not args.no_write)
        if not result.get("ok"):
            print(json.dumps({"refresh_census": result}, indent=2))

    state = build_state()
    if args.compact:
        for s in state["ev_curves"]["series"]:
            s["points"] = f"<{len(s['points'])} points elided>"
    print(json.dumps(state, indent=2, default=str))


if __name__ == "__main__":
    _main()
