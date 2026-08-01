#!/usr/bin/env python3
"""B11a — the fresh evaluation window: re-derivation, disjointness, preflight and orchestration.

Offline except for ONE permitted RPC method. No UI, no server, no model, no signal, no wallet, no
signing, no paid subscription. Freeze: `research/B11A_FRESH_COHORT_PREREGISTRATION.json`, committed
alone before any chain query.

This module does four things, and refuses a fifth.

1. **Re-derives the window from the burned-range register**, independently of the committed
   document, and refuses if the two disagree by even one slot. The preregistration is the authority;
   this is the check that it has not drifted, not the thing that produced it.
2. **Checks disjointness** of both the launch window and the whole observation span against all
   seven burned ranges, failing closed.
3. **Runs a maturity preflight** using exactly one RPC method. `getSlot` is on an allowlist and
   every other method is refused by name, so a composition query cannot be issued from here even by
   accident — `getSignaturesForAddress` and `getBlock` would reveal what is *in* the window, and
   what is in the window is the thing nobody may look at yet.
4. **Plans the collection pipeline** so it can start at maturity, with each stage declaring whether
   it may run before results are unlocked and whether its output is composition.

**It refuses to report any composition figure.** Every stage that emits one is either forbidden
before unlock or has its numbers withheld, because a census, a yield count or a label distribution
on this window before models and thresholds are frozen burns it — abort branch A7.

WHY THE WINDOW IS NOT MOVED, EVER
=================================

If the cutoff is not mature, this module reports the wait. It does not shorten the observation span,
does not slide the launch window earlier, and does not substitute a nearer window. A window moved
because the frozen one was inconvenient is a chosen window, and a chosen window is not evidence.
"""
import argparse
import hashlib
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREREGISTRATION_PATH = ROOT / "research" / "B11A_FRESH_COHORT_PREREGISTRATION.json"

# The committed bytes of the freeze. Pinned here so a silently edited preregistration fails the
# check rather than redefining the window it is supposed to fix.
PREREGISTRATION_FILE_SHA256 = (
    "5faabb33ad317240824450a9b8a3a4026137a04e4457b4767e95488a5c469ac0")
PREREGISTRATION_CANONICAL_SHA256 = (
    "ae4d2f0351aaba193fe7d87cde8cd68ce83aa8d21515d4d20af0a158f8dafe9f")

# The burned-range register, restated here from `DECISIONS.md` so this module can re-derive the
# window WITHOUT reading the document it is checking. A checker that takes its inputs from the thing
# under test cannot detect drift in it.
#
# `half_open` means the source wrote `[a, b)`. Where a document's burn STATEMENT is wider than the
# code range it describes, the wider statement governs: B7b scanned `range(435566652, 435566690)`
# but declared "Slots 435,566,652 - 435,566,690 are BURNED", and the reading that keeps a slot out
# of evaluation is the one to take.
BURNED_RANGES = (
    ("B7e mature cohort", 429_998_000, 430_000_000, "half_open"),
    ("B7d engineering pilot", 430_000_000, 430_000_500, "half_open"),
    ("B8a cohort", 433_302_364, 433_304_364, "half_open"),
    ("B8b cohort (also the B9d/B10b/B10c corpus)", 433_894_233, 434_097_833, "inclusive"),
    ("B7j/B7k positive-control envelope", 435_564_885, 435_565_324, "half_open"),
    ("B7b dead-threshold sample", 435_566_652, 435_566_690, "inclusive"),
    ("B7c trade-only gap sample", 435_569_119, 435_569_149, "inclusive"),
)

# The two inherited spans' inputs, from artifact metadata rather than prose.
B8B_WINDOW_START_SLOT = 433_894_233
B8B_WINDOW_END_SLOT_INCLUSIVE = 434_097_833
B9D_CUTOFF_SLOT = 435_536_742

# Estimate basis only. 2.3934 slots/s was measured on 438 consecutive B7j blocks over 183 s; it is
# an existing artifact, and a wall-clock figure derived from it is an ESTIMATE, never a commitment.
SLOTS_PER_SECOND = 2.3934

# The one method this module may call. Everything else reveals what is inside the window.
PREFLIGHT_ALLOWED_METHODS = ("getSlot",)

STAGE_COLLECTION = "collection"
STAGE_GATE = "gate"
STAGE_RESULTS = "results"


class WindowRefused(Exception):
    """Raised when the frozen window cannot be honoured exactly as frozen."""


# --------------------------------------------------------------------------------------------
# Derivation and disjointness
# --------------------------------------------------------------------------------------------

def normalized_burned_ranges(ranges=BURNED_RANGES):
    """`(origin, inclusive_first, inclusive_last)` for every burned range."""
    out = []
    for origin, first, last, convention in ranges:
        if convention == "inclusive":
            inclusive_last = last
        elif convention == "half_open":
            inclusive_last = last - 1
        else:
            raise WindowRefused(
                f"{origin}: unknown range convention {convention!r}; a range whose convention is "
                "not stated is a range whose endpoint is a guess")
        if inclusive_last < first:
            raise WindowRefused(f"{origin}: empty range [{first}, {inclusive_last}]")
        out.append((origin, first, inclusive_last))
    return out


def derive_window(ranges=BURNED_RANGES):
    """Recompute all four endpoints from the register and the two inherited spans.

    Independent of the committed document on purpose. This is the arithmetic anyone can redo by
    hand; `assert_matches_preregistration` is what compares it to what was frozen.
    """
    normalized = normalized_burned_ranges(ranges)
    maximum = max(last for _, _, last in normalized)
    launch_span = B8B_WINDOW_END_SLOT_INCLUSIVE - B8B_WINDOW_START_SLOT + 1
    observation_span = B9D_CUTOFF_SLOT - B8B_WINDOW_START_SLOT
    start = maximum + 1
    return {
        "maximum_inclusive_burned_endpoint": maximum,
        "launch_window_span_slots": launch_span,
        "observation_span_slots": observation_span,
        "launch_window_first_slot_inclusive": start,
        "launch_window_last_slot_inclusive": start + launch_span - 1,
        "observation_cutoff_slot_inclusive": start + observation_span,
    }


def assert_disjoint(first, last, ranges=BURNED_RANGES):
    """No intersection with any burned range. Overlap aborts; it never shifts the window."""
    if last < first:
        raise WindowRefused(f"span [{first}, {last}] is empty")
    hits = [(origin, low, high) for origin, low, high in normalized_burned_ranges(ranges)
            if not (last < low or high < first)]
    if hits:
        raise WindowRefused(
            f"span [{first}, {last}] intersects burned range(s) {hits}. ABORT — the window is "
            "never shifted to avoid an overlap, because a shifted window is a chosen window")
    return True


def load_preregistration(path=PREREGISTRATION_PATH, verify_hashes=True):
    """Read the freeze and verify it is byte-for-byte the document that was committed."""
    raw = pathlib.Path(path).read_bytes()
    document = json.loads(raw)
    if verify_hashes:
        digest = hashlib.sha256(raw).hexdigest()
        canonical = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if digest != PREREGISTRATION_FILE_SHA256:
            raise WindowRefused(
                f"preregistration file hash is {digest}, pinned {PREREGISTRATION_FILE_SHA256}; the "
                "frozen document has been edited and no longer fixes the window it claims to")
        if canonical != PREREGISTRATION_CANONICAL_SHA256:
            raise WindowRefused(
                f"preregistration canonical hash is {canonical}, pinned "
                f"{PREREGISTRATION_CANONICAL_SHA256}")
    return document


def assert_matches_preregistration(document=None, ranges=BURNED_RANGES):
    """Re-derived endpoints must equal the frozen ones exactly. One slot of drift is a failure."""
    document = document if document is not None else load_preregistration()
    derived = derive_window(ranges)
    frozen = document["frozen_window"]
    register = document["burned_range_register"]

    if register["count"] != len(ranges):
        raise WindowRefused(
            f"the register lists {register['count']} burned ranges, this module knows "
            f"{len(ranges)}; a range added or dropped changes the window")
    if register["maximum_inclusive_endpoint"] != derived["maximum_inclusive_burned_endpoint"]:
        raise WindowRefused(
            f"maximum burned endpoint drifted: frozen {register['maximum_inclusive_endpoint']}, "
            f"re-derived {derived['maximum_inclusive_burned_endpoint']}")
    for origin, first, last in normalized_burned_ranges(ranges):
        entry = next((r for r in register["ranges"] if r["inclusive_first"] == first), None)
        if entry is None or entry["inclusive_last"] != last:
            raise WindowRefused(
                f"{origin}: register entry [{first}, {last}] is missing or has a different "
                "endpoint; an off-by-one here moves the whole window")

    for field in ("launch_window_first_slot_inclusive", "launch_window_last_slot_inclusive",
                  "observation_cutoff_slot_inclusive"):
        if frozen[field] != derived[field]:
            raise WindowRefused(
                f"{field} drifted: frozen {frozen[field]}, re-derived {derived[field]}")
    if frozen["observation_window_end_slot"] != frozen["observation_cutoff_slot_inclusive"]:
        raise WindowRefused("the label window end and the collection cutoff disagree")

    derivation = document["derivation"]
    if derivation["launch_window_span_slots"]["value"] != derived["launch_window_span_slots"]:
        raise WindowRefused("launch window span drifted from the inherited B8b geometry")
    if derivation["observation_span_slots"]["value"] != derived["observation_span_slots"]:
        raise WindowRefused("observation span drifted from the inherited B9d geometry")

    assert_disjoint(frozen["launch_window_first_slot_inclusive"],
                    frozen["launch_window_last_slot_inclusive"], ranges)
    # REDUNDANT, and said so rather than left to look load-bearing. The start rule is
    # `max(burned last) + 1`, so every burned range ends strictly before the window begins and
    # nothing can reach into [start, cutoff]. A mutation deleting this line therefore SURVIVES the
    # suite by construction; that is recorded in the research note rather than papered over with a
    # test that cannot really fail. It is kept because it costs nothing and it is what would catch
    # a future change to the start rule that the drift checks happened to miss.
    assert_disjoint(frozen["launch_window_first_slot_inclusive"],
                    frozen["observation_cutoff_slot_inclusive"], ranges)
    return derived


# --------------------------------------------------------------------------------------------
# Preflight — one method, and no way to call a second
# --------------------------------------------------------------------------------------------

def _endpoint_reference(url):
    """Scheme and host only. An API key lives in the query string or the path; neither is kept."""
    parsed = urllib.parse.urlsplit(url)
    return f"{parsed.scheme}://{parsed.hostname}/"


def _default_transport(url, method, params, timeout=30):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                      separators=(",", ":")).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read())
    if "error" in payload:
        raise WindowRefused(f"RPC error: {payload['error']}")
    return payload.get("result")


def preflight_call(url, method, params, transport=None):
    """The only door out to the network, and it is an allowlist.

    A denylist would need to anticipate every method that leaks composition. An allowlist needs to
    anticipate nothing: `getSignaturesForAddress`, `getBlock`, `getProgramAccounts` and everything
    else are refused because they are not `getSlot`.
    """
    if method not in PREFLIGHT_ALLOWED_METHODS:
        raise WindowRefused(
            f"method {method!r} is not in the preflight allowlist {list(PREFLIGHT_ALLOWED_METHODS)}."
            " Anything else would reveal what is inside the frozen window, and what is inside the "
            "window is the one thing nobody may look at before models and thresholds are frozen")
    return (transport or _default_transport)(url, method, params)


def rpc_url_from_environment():
    url = os.environ.get("SOLANA_RPC_URL")
    if not url:
        raise WindowRefused(
            "REFUSING: SOLANA_RPC_URL is not set. Credentials are environment-only and are never "
            "written to a file, a report or this repository")
    return url


def maturity(tip_slot, document=None):
    """Is the frozen cutoff reached, and if not, exactly how far away is it?

    The wall-clock figure is an ESTIMATE from a measured slot rate, and is labelled so. The slot
    count is exact and is the number that matters: it does not move if the network speeds up.
    """
    document = document if document is not None else load_preregistration()
    cutoff = document["frozen_window"]["observation_cutoff_slot_inclusive"]
    if isinstance(tip_slot, bool) or not isinstance(tip_slot, int) or tip_slot < 0:
        raise WindowRefused(f"tip slot must be a non-negative integer, got {tip_slot!r}")
    remaining = cutoff - tip_slot
    if remaining <= 0:
        return {"mature": True, "tip_slot": tip_slot, "cutoff_slot": cutoff,
                "slots_remaining": 0, "estimated_wait_seconds": 0,
                "estimated_wait_days": 0, "estimate_basis": None, "action": "collection may begin"}
    seconds = remaining / SLOTS_PER_SECOND
    return {
        "mature": False, "tip_slot": tip_slot, "cutoff_slot": cutoff,
        "slots_remaining": remaining,
        "estimated_wait_seconds": round(seconds),
        "estimated_wait_days": round(seconds / 86400, 2),
        "estimate_basis": f"{SLOTS_PER_SECOND} slots/s measured on 438 consecutive B7j blocks "
                          "over 183 s; an estimate, not a commitment",
        "action": "WAIT. The window is not moved, not shortened and not re-placed (abort branch A3)",
    }


def preflight(url=None, transport=None, document=None):
    """One `getSlot` at finalized commitment. Nothing else, by construction."""
    document = document if document is not None else load_preregistration()
    assert_matches_preregistration(document)
    url = url or rpc_url_from_environment()
    tip = preflight_call(url, "getSlot", [{"commitment": "finalized"}], transport)
    if not isinstance(tip, int):
        raise WindowRefused(f"getSlot returned {tip!r}, which is not a slot")
    receipt = {
        "preregistration_id": document["preregistration_id"],
        "preregistration_file_sha256": PREREGISTRATION_FILE_SHA256,
        "preregistration_canonical_sha256": PREREGISTRATION_CANONICAL_SHA256,
        "endpoint_reference": _endpoint_reference(url),
        "methods_called": ["getSlot"],
        "composition_queried": False,
        "frozen_window": dict(document["frozen_window"]),
        "maturity": maturity(tip, document),
    }
    return receipt


def assert_preregistration_unchanged(receipt, document=None):
    """The window may not change after a preflight has observed the chain.

    Once the tip has been looked at, any edit to the endpoints is a window chosen with knowledge of
    where the chain currently is. Abort branch A5: that requires a NEW preregistration with a new
    identifier, and this one is then burned.
    """
    document = document if document is not None else load_preregistration()
    frozen = document["frozen_window"]
    if receipt.get("preregistration_file_sha256") != PREREGISTRATION_FILE_SHA256:
        raise WindowRefused(
            "the preregistration hash changed after a preflight; the window was edited with the "
            "chain's current position in view (abort branch A5)")
    for field, value in receipt.get("frozen_window", {}).items():
        if frozen.get(field) != value:
            raise WindowRefused(
                f"{field} changed after the preflight: receipt {value}, document "
                f"{frozen.get(field)} (abort branch A5)")
    return True


# --------------------------------------------------------------------------------------------
# Orchestration plan
# --------------------------------------------------------------------------------------------

# The existing pipeline, in order, each stage declaring what it is allowed to do before results are
# unlocked. `emits_composition` is separate from `permitted_before_unlock` because a gate must be
# able to FAIL before unlock — you cannot ship data you have not gated — while its counts are still
# a description of the window and must be withheld.
PIPELINE = (
    # Note on `emits_composition` for the collection stages. Enumerating the cohort produces its
    # membership list, and a membership COUNT is a description of the window even though fetching
    # it is unavoidable — you cannot collect a cohort without knowing who is in it. So collection
    # runs, and its counts are withheld, exactly as a gate's are. Only the program-boundary probe is
    # composition-free: an upgrade slot is a property of the program, not of this cohort.
    {"stage": "enumerate_creates", "script": "b7d_create_enumerator.py",
     "kind": STAGE_COLLECTION, "permitted_before_unlock": True, "emits_composition": True,
     "note": "exhaustive CreateEvent enumeration over the launch window (C4); no filtering"},
    {"stage": "signature_inventory", "script": "b9c_signature_inventory.py",
     "kind": STAGE_COLLECTION, "permitted_before_unlock": True, "emits_composition": True,
     "note": "per-curve signature pages, raw responses preserved byte-exact"},
    {"stage": "transaction_bodies", "script": "b9d_transaction_bodies.py",
     "kind": STAGE_COLLECTION, "permitted_before_unlock": True, "emits_composition": True,
     "note": "raw transaction bodies preserved before any decode"},
    {"stage": "program_boundary", "script": "b9d_transaction_bodies.py --boundary",
     "kind": STAGE_COLLECTION, "permitted_before_unlock": True, "emits_composition": False,
     "note": "upgrade-boundary evidence for both programs; abort branch A2 is decided here. The "
             "only composition-free stage: an upgrade slot is a property of the program"},
    {"stage": "decode_and_reserves", "script": "b9d_transaction_bodies.py --decode",
     "kind": STAGE_COLLECTION, "permitted_before_unlock": True, "emits_composition": True,
     "note": "pinned-IDL decode and reserve reconstruction"},
    {"stage": "reserve_coverage_gate", "script": "b9e_reserve_coverage.py",
     "kind": STAGE_GATE, "permitted_before_unlock": True, "emits_composition": True,
     "note": "must pass or fail before the data is usable; its counts describe the window"},
    {"stage": "failure_coverage_gate", "script": "b9f_failure_coverage.py",
     "kind": STAGE_GATE, "permitted_before_unlock": True, "emits_composition": True,
     "note": "as above"},
    {"stage": "simulator_replay_gate", "script": "b10a_simulator_kernel.py --gate",
     "kind": STAGE_GATE, "permitted_before_unlock": True, "emits_composition": True,
     "note": "integer replay must reproduce this window's trades exactly"},
    {"stage": "position_paths", "script": "b10b_path_dataset.py",
     "kind": STAGE_RESULTS, "permitted_before_unlock": False, "emits_composition": True,
     "note": "path marks and drawdowns are outcomes"},
    {"stage": "outcome_labels", "script": "b10c_label_corpus.py",
     "kind": STAGE_RESULTS, "permitted_before_unlock": False, "emits_composition": True,
     "note": "labels are the thing that must stay sealed until models and thresholds are frozen"},
)


def plan_pipeline(mature, results_unlocked=False):
    """What may run now, and what may not, with the reason attached to each refusal."""
    plan = []
    for stage in PIPELINE:
        if not mature:
            runnable, reason = False, (
                "the frozen observation cutoff is not mature; waiting does not move the window "
                "(abort branch A3)")
        elif not stage["permitted_before_unlock"] and not results_unlocked:
            runnable, reason = False, (
                "results are locked: computing this before models, horizons and thresholds are "
                "frozen and recorded in DECISIONS.md would burn the window (abort branch A7)")
        else:
            runnable, reason = True, None
        plan.append({**stage, "runnable": runnable, "blocked_reason": reason,
                     "numbers_withheld": stage["emits_composition"] and not results_unlocked})
    return plan


def assert_stage_permitted(stage_name, mature, results_unlocked=False):
    """Refuse a stage that may not run yet, by name, with the branch that forbids it."""
    entry = next((s for s in plan_pipeline(mature, results_unlocked)
                  if s["stage"] == stage_name), None)
    if entry is None:
        raise WindowRefused(f"unknown pipeline stage {stage_name!r}")
    if not entry["runnable"]:
        raise WindowRefused(f"stage {stage_name!r} refused: {entry['blocked_reason']}")
    return entry


def redact_composition(report, results_unlocked=False):
    """Withhold the numbers a gate produced about the window, keeping only pass/fail.

    A pass/fail is one bit about the window and is unavoidable — data that has not been gated cannot
    be shipped. A count is a description of its composition, and descriptions are what burn it.
    """
    if results_unlocked:
        return report
    return {"composition_withheld": True,
            "reason": "counts describing this window are sealed until models, horizons and "
                      "thresholds are frozen and recorded in DECISIONS.md (abort branch A7)",
            "passed": bool(report.get("passed"))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("verify")
    flight = subparsers.add_parser("preflight")
    flight.add_argument("--out", default=str(ROOT / "research" / "B11A_PREFLIGHT.json"))
    planner = subparsers.add_parser("plan")
    planner.add_argument("--mature", action="store_true")
    args = parser.parse_args(argv)

    document = load_preregistration()
    if args.command == "verify":
        derived = assert_matches_preregistration(document)
        print(json.dumps({"preregistration_id": document["preregistration_id"],
                          "file_sha256": PREREGISTRATION_FILE_SHA256,
                          "canonical_sha256": PREREGISTRATION_CANONICAL_SHA256,
                          "re_derived": derived, "matches_frozen": True,
                          "disjoint_from_all_burned_ranges": True}, indent=2, sort_keys=True))
        return 0
    if args.command == "plan":
        print(json.dumps(plan_pipeline(args.mature), indent=2, sort_keys=True))
        return 0

    receipt = preflight(document=document)
    assert_preregistration_unchanged(receipt, document)
    receipt["pipeline"] = plan_pipeline(receipt["maturity"]["mature"])
    pathlib.Path(args.out).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except WindowRefused as error:
        print(f"WindowRefused: {error}", file=sys.stderr)
        sys.exit(2)
