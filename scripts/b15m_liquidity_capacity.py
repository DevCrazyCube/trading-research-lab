"""B15m — how much external liquidity was there to exit into, exactly.

Implements `research/B15M_LIQUIDITY_CAPACITY_PREREGISTRATION.json`, committed alone before any
capacity here was computed.

B15L found the observed book could pay for the exit on only 19% of cells. 0.1 SOL was fixed long
before those curves existed and was never chosen with them in view, so the question that follows is
not what that size would have yielded but how much liquidity there was to sell into at all.

**External only.** The exit is priced against the exit checkpoint exactly as observed. Our own buy
adds nothing to the reserves it would later be paid out of. A cell whose sale was payable only from
what our own purchase contributed is named `circular_liquidity_dependence`, because an exit funded by
one's own entry is not liquidity.

**Bisection is earned, not assumed.** `tokens_out` is non-decreasing in the quote input and
`quote_out` is non-decreasing in tokens, so each constraint defines a down-set and the admissible
inputs form a prefix. That argument is easy, which is exactly why the returned answer is still
checked against both constraints, and the next integer against at least one, on every cell.

**Nothing here is a return, and nothing here is a recommended size.** A capacity is what the book
could have absorbed. No size is selected, ranked or called optimal.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"

WORK_DIR = ROOT / "research" / "b15m"
PREREG_PATH = ROOT / "research" / "B15M_LIQUIDITY_CAPACITY_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "3feca3846ce544d1e97ce7bb7691e06bbf988b3d00c2d26122e27c3f4fd53d4a"

EXECUTION_SURFACE_TOKENS = ("sendTransaction", "signTransaction", "Keypair", "from_secret_key",
                            "private_key", "secret_key", "sign_message", "PRIVATE_KEY",
                            "WALLET", "mnemonic", "seed_phrase", "requestAirdrop",
                            "simulateTransaction")

FORBIDDEN_OUTPUT_WORDS = ("return", "profit", "pnl", "expected_value", "roi", "performance",
                          "gain", "earnings", "yield", "optimal", "recommended", "best")
STATUS_LOCK_KEYS = ("performance_status", "execution_status")

M_NOT_IN_B15L_UNIVERSE = "M_NOT_IN_B15L_UNIVERSE"
M_NON_MONOTONE = "M_NON_MONOTONE"
M_MAXIMALITY_UNPROVEN = "M_MAXIMALITY_UNPROVEN"
M_CONSTRAINT_VIOLATED = "M_CONSTRAINT_VIOLATED"
M_IMPOSSIBLE_RESERVES = "M_IMPOSSIBLE_RESERVES"
M_FLOAT_PRESENT = "M_FLOAT_PRESENT"
M_DIFFERENTIAL_DISAGREEMENT = "M_DIFFERENTIAL_DISAGREEMENT"

LABEL = "LIQUIDITY_CAPACITY_DIAGNOSTIC"
CIRCULAR = "circular_liquidity_dependence"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B15L = _load("b15l_counterfactual_roundtrip", "b15l_counterfactual_roundtrip.py")
B10B = _load("b10b_position_path", "b10b_position_path.py")
B10A, B9I = B15L.B10A, B15L.B9I
NATIVE_QUOTE_MINT = B15L.NATIVE_QUOTE_MINT
CENSORING_STATEMENT = B15L.CENSORING_STATEMENT


class CapacityRefused(RuntimeError):
    """This cell yields no capacity, and the reason is recorded rather than defaulted to zero."""


def verify_preregistration(path=PREREG_PATH, expected_sha256=None):
    expected = PREREG_CANONICAL_SHA256 if expected_sha256 is None else expected_sha256
    try:
        document = json.loads(pathlib.Path(path).read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise CapacityRefused(f"cannot read the preregistration {path}: {error}") from error
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise CapacityRefused(f"the capacity preregistration hashes {actual}, pinned {expected}")
    return document


def assert_no_execution_surface(path=None):
    path = pathlib.Path(__file__) if path is None else pathlib.Path(path)
    text = path.read_text()
    marker = "STATUS_LOCK_KEYS = (" if "STATUS_LOCK_KEYS = (" in text \
        else "EXECUTION_SURFACE_TOKENS = ("
    body = text.split(marker, 1)[-1].split(")", 1)[-1]
    found = sorted({token for token in EXECUTION_SURFACE_TOKENS if token in body})
    if found:
        raise CapacityRefused(f"an execution surface appeared in {path.name}: {found}")
    return True


def assert_no_forbidden_words(report):
    """No FIELD may be named after a return, or after a recommendation.

    `optimal`, `recommended` and `best` are here for the same reason as `profit`: this study reports
    what the book could absorb, and a field called `recommended_size` would turn that into advice
    no matter what the label above it said.
    """
    found = set()
    for key in B15L._keys(report):
        if key in STATUS_LOCK_KEYS:
            continue
        parts = set(str(key).lower().split("_"))
        for word in FORBIDDEN_OUTPUT_WORDS:
            if set(word.split("_")) <= parts:
                found.add(word)
    if found:
        raise CapacityRefused(
            f"the report names a field after {sorted(found)}; this study reports capacity, not a "
            f"return and not a recommendation")
    return True


def assert_integer(label, value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise CapacityRefused(f"{M_FLOAT_PRESENT}: {label} is {value!r}, not an integer")
    return value


# --------------------------------------------------------------------------------------------
# The predicate and the search
# --------------------------------------------------------------------------------------------

def tokens_for(entry, quote_in):
    """What a buy of `quote_in` acquires at the entry checkpoint. B9I's pinned formula, by call."""
    if quote_in <= 0:
        return 0
    return B9I.tokens_out_for_exact_quote_in(
        entry["virtual_quote"], entry["virtual_token"], quote_in)


def gross_draw(entry, exit_state, quote_in):
    """What selling this input's tokens would draw from the OBSERVED exit reserves.

    Non-decreasing in `quote_in`, which is the property both searches below rely on.
    """
    tokens = tokens_for(entry, quote_in)
    if tokens <= 0:
        return 0
    return B9I.quote_out_for_tokens_in(
        exit_state["virtual_quote"], exit_state["virtual_token"], tokens)


def is_payable(entry, exit_state, quote_in):
    """The DOWN-SET condition: the reserves can cover this size on both legs.

    Kept separate from `is_admissible` because only this half is monotone downward, and only a
    down-set can be bisected. Mixing in the lower bound below produced an interval, and bisecting an
    interval finds its top by luck rather than by construction.
    """
    if quote_in == 0:
        return True
    tokens = tokens_for(entry, quote_in)
    if tokens > entry["real_token"]:
        return False
    return gross_draw(entry, exit_state, quote_in) <= exit_state["real_quote"]


def is_admissible(entry, exit_state, quote_in):
    """Payable AND worth something. Both constraints, against the OBSERVED exit reserves.

    The lower bound is B10b's own rule, adopted rather than invented: a size whose gross proceeds
    are zero is `L1M_NO_EXECUTABLE_SIZE` there, because nothing that cannot be sold for even one
    lamport is liquidity. Without it an empty book reported a capacity of two lamports — a buy whose
    tokens sell for nothing, which any reserve can trivially pay.

    Nothing our buy would have added to the curve is available to pay for our sale. That is the
    whole point of the estimand: B15L already measured what happens when it is.
    """
    if quote_in == 0:
        return True
    if not is_payable(entry, exit_state, quote_in):
        return False
    return gross_draw(entry, exit_state, quote_in) >= 1


def assert_reserves_possible(state, label):
    for field in ("virtual_quote", "virtual_token", "real_quote", "real_token"):
        assert_integer(f"{label} {field}", state[field])
    if state["virtual_quote"] <= 0 or state["virtual_token"] <= 0:
        raise CapacityRefused(
            f"{M_IMPOSSIBLE_RESERVES}: {label} virtual reserves "
            f"({state['virtual_quote']}, {state['virtual_token']}) are non-positive")
    if state["real_quote"] < 0 or state["real_token"] < 0:
        raise CapacityRefused(
            f"{M_IMPOSSIBLE_RESERVES}: {label} real reserves are negative")
    return True


def minimum_effective_quote(entry, ceiling):
    """The smallest quote input that acquires at least one token, or None if none does.

    This exists because the admissible set is NOT a prefix of [0, ceiling], and the reason has
    nothing to do with liquidity. The pinned exact-input formula has `(q - 1)` in its numerator, so
    a one-lamport buy acquires zero tokens at any reserves — B10a refuses it as "below the curve's
    resolution rather than merely small". The admissible set is therefore {0} together with a
    contiguous run starting at this floor, and bisecting over [0, ceiling] would search a set that
    is not a prefix.

    The ESTIMAND is unchanged: the greatest admissible input is the same number either way, because
    the maximum of {0} and a run above the floor is the top of that run. Only the search domain is
    corrected, and the floor itself is published rather than hidden.

    `tokens_for` is non-decreasing in q, so this bound is itself found by a valid bisection.
    """
    if tokens_for(entry, ceiling) < 1:
        return None
    low, high = 1, ceiling
    while low < high:
        middle = (low + high) // 2
        if tokens_for(entry, middle) >= 1:
            high = middle
        else:
            low = middle + 1
    return low


def external_capacity(entry, exit_state, ceiling):
    """The greatest admissible quote input, with maximality PROVEN on the result.

    Bisection relies on the admissible inputs forming a prefix. The argument for that is short, so
    the answer is checked rather than trusted: `q` must satisfy both constraints, and `q+1` must
    violate at least one unless `q` is the ceiling. A search that returned a non-maximal answer, or
    an answer over a set that is not a prefix, refuses instead of reporting.
    """
    assert_integer("ceiling", ceiling)
    assert_reserves_possible(entry, "entry")
    assert_reserves_possible(exit_state, "exit")
    floor = minimum_effective_quote(entry, ceiling)
    if floor is None or not is_payable(entry, exit_state, floor):
        # No positive buy this book could pay to exit. Zero is a finding, not missing data.
        return 0
    # Bisect on the DOWN-SET only. The full admissibility condition is an interval, and the maximum
    # of an interval is the maximum of its down-set half whenever the interval is non-empty.
    low, high = floor, ceiling
    while low < high:
        middle = (low + high + 1) // 2
        if is_payable(entry, exit_state, middle):
            low = middle
        else:
            high = middle - 1
    if gross_draw(entry, exit_state, low) < 1:
        # Payable, and worth nothing. B10b calls this no executable size; so does this study.
        return 0
    assert_maximal(entry, exit_state, low, ceiling)
    return low


def assert_maximal(entry, exit_state, capacity, ceiling):
    """The two post-conditions, as a named function with its own tests.

    Kept separate from the search because a guard reached only through a correct search is a guard
    nobody can provoke, and B10b already learned that lesson the expensive way: a mutant flipping an
    inclusive comparison survived a whole mutation run until the rule became a named function.
    """
    if not is_admissible(entry, exit_state, capacity):
        raise CapacityRefused(
            f"{M_CONSTRAINT_VIOLATED}: the search returned {capacity}, which does not satisfy the "
            f"constraints it was searching under")
    if capacity < ceiling and is_admissible(entry, exit_state, capacity + 1):
        raise CapacityRefused(
            f"{M_MAXIMALITY_UNPROVEN}: {capacity + 1} is also admissible but {capacity} was "
            f"returned; the search did not find the maximum")
    return True


def capacity_via_b10b(entry, exit_state, ceiling):
    """The same quantity by a different route, for the differential check.

    B10b's `max_executable_tokens` finds the largest TOKEN amount the observed reserve can pay for,
    with its own maximality proof. Because `quote_out_for_tokens_in` is non-decreasing, "the exit is
    payable" and "the tokens do not exceed that maximum" are the SAME condition — so searching over
    the quote input and searching over tokens must agree. The test therefore checks a theorem
    rather than a coincidence.
    """
    held = tokens_for(entry, ceiling)
    token_cap, _gross = B10B.max_executable_tokens(
        exit_state["virtual_quote"], exit_state["virtual_token"], exit_state["real_quote"], held)
    limit = min(token_cap, entry["real_token"])
    floor = minimum_effective_quote(entry, ceiling)
    if floor is None or not 0 < tokens_for(entry, floor) <= limit:
        return 0
    low, high = floor, ceiling
    while low < high:
        middle = (low + high + 1) // 2
        tokens = tokens_for(entry, middle)
        if 0 < tokens <= limit:
            low = middle
        else:
            high = middle - 1
    if not 0 < tokens_for(entry, low) <= limit:
        return 0
    # The same zero-gross rule, so the two routes are comparing the same quantity.
    if gross_draw(entry, exit_state, low) < 1:
        return 0
    return low


def self_contributed_exit_payable(entry, exit_state, position_lamports):
    """Could B15L price this cell's exit, using our own buy's contribution to the reserves?

    Cost-policy free on purpose. Payability is a reserve question — `quote_out > real_quote` — and
    depends on neither the fee schedule nor the priority fee, so a diagnostic that took a policy
    would invite the reading that it varies by scenario when it does not.
    """
    tokens = tokens_for(entry, position_lamports)
    if tokens <= 0 or tokens > entry["real_token"]:
        return False
    try:
        transported, _external, _ours = B15L.counterfactual_exit_state(
            entry, exit_state, tokens, position_lamports)
    except B15L.CounterfactualRefused:
        return False
    draw = B9I.quote_out_for_tokens_in(
        transported["virtual_quote"], transported["virtual_token"], tokens)
    return draw <= transported["real_quote"]


def assert_prefix_shape(entry, exit_state, ceiling, samples=None):
    """Above the resolution floor the admissible set must be a contiguous run. Scanned by hand.

    This is the assumption bisection rests on, so on a small ceiling it is checked by brute force
    rather than argued. Two things are asserted, not one:

    - every input below the floor acquires ZERO tokens, so its inadmissibility is the curve's
      resolution and not a liquidity gap;
    - from the floor upward, admissibility never returns once it has stopped.
    """
    limit = ceiling if samples is None else min(ceiling, samples)
    floor = minimum_effective_quote(entry, limit)
    if floor is None:
        return True
    for quote_in in range(1, floor):
        if tokens_for(entry, quote_in) != 0:
            raise CapacityRefused(
                f"{M_NON_MONOTONE}: {quote_in} is below the computed resolution floor {floor} but "
                f"acquires tokens; the floor is wrong")
    seen_false = False
    for quote_in in range(floor, limit + 1):
        # The PAYABILITY half is the one that must be a prefix; full admissibility is an interval
        # by construction, because a size can be too small to be worth anything.
        admissible = is_payable(entry, exit_state, quote_in)
        if admissible and seen_false:
            raise CapacityRefused(
                f"{M_NON_MONOTONE}: {quote_in} is admissible although a smaller input above the "
                f"floor was not; the admissible set is not a contiguous run and bisection is not "
                f"valid here")
        if not admissible:
            seen_false = True
    return True


# --------------------------------------------------------------------------------------------
# The fixed grid, and the costs
# --------------------------------------------------------------------------------------------

# The bodies `research/B15M_PAYABILITY_DOWNSET_PROOF.md` was written against. A proof certifies
# SOURCE, so the source it certifies is pinned; drift re-arms the scan rather than silently
# detaching the argument from the code it is about.
PROVEN_BODIES = {
    "b9i.tokens_out_for_exact_quote_in":
        "86b5fac0c9bafa50bdf237bcc6bccfd73129932f4375f4fe9870da4da000e6a7",
    "b9i.quote_out_for_tokens_in":
        "f40a46b73025732cec97bbb590a864bd0de0de2fb919ecda3ec9c51a3430a832",
    "b15m.tokens_for":
        "abcbbeee367c7e347928a00283c16b64edc81db54c9106989a91d7580dc15810",
    "b15m.gross_draw":
        "9c74e8651dfa3de4625c8717e508dc8f7138dacd17c2aefdf64bef67125631ad",
    "b15m.is_payable":
        "f109e45fd88314e31be770a7e3553788c17a40d3f61e305872f5942c356cfaf8",
    "b15m.assert_reserves_possible":
        "4d6d1d1fa871d634b613aae88197108e4e9a2a788ab1bf9f1427dc6e5cdb2ba3",
}


def _body_digests():
    """sha256 of each function body the down-set proof depends on, by inspection of live source."""
    import inspect
    return {
        "b9i.tokens_out_for_exact_quote_in": hashlib.sha256(
            inspect.getsource(B9I.tokens_out_for_exact_quote_in).encode()).hexdigest(),
        "b9i.quote_out_for_tokens_in": hashlib.sha256(
            inspect.getsource(B9I.quote_out_for_tokens_in).encode()).hexdigest(),
        "b15m.tokens_for": hashlib.sha256(inspect.getsource(tokens_for).encode()).hexdigest(),
        "b15m.gross_draw": hashlib.sha256(inspect.getsource(gross_draw).encode()).hexdigest(),
        "b15m.is_payable": hashlib.sha256(inspect.getsource(is_payable).encode()).hexdigest(),
        "b15m.assert_reserves_possible": hashlib.sha256(
            inspect.getsource(assert_reserves_possible).encode()).hexdigest(),
    }


def proof_binding_intact(pinned=None):
    """Do the functions the proof is ABOUT still have the bodies it was written against?

    The proof certifies four short function bodies as they are written today. The scan executes the
    actual predicate every time. That difference is the whole risk: a fee folded into `tokens_for`,
    or a rounding change after the next program revision, would silently detach the proof while
    every test still passed.

    So the binding is machine-checked rather than remembered. Returns (True, {}) when every body
    matches, else (False, {name: (pinned, actual)}) naming exactly what moved.
    """
    pinned = PROVEN_BODIES if pinned is None else pinned
    actual = _body_digests()
    drifted = {name: (pinned.get(name), digest) for name, digest in actual.items()
               if pinned.get(name) != digest}
    return (not drifted), drifted


def assert_prefix_shape_by_theorem(entry, exit_state, ceiling, samples=None, pinned=None):
    """The prefix property, established by proof rather than by a ten-billion-step scan.

    See `research/B15M_PAYABILITY_DOWNSET_PROOF.md`. Under `virtual_quote >= 1` and
    `virtual_token >= 1` on BOTH states, `tokens_for` and `gross_draw` are non-decreasing in the
    quote input, so payability is a down-set and the resolution floor is a prefix. Both halves of
    what the scan asserts follow from one monotonicity lemma.

    THE HYPOTHESES ARE DISCHARGED HERE, not by the caller. `b19c.capacity` happens to call
    `assert_reserves_possible` before the scan today, but that is a POSITIONAL guarantee: reorder
    the calls and the proof loses its hypothesis silently. Calling it here makes the guarantee
    local to the thing that depends on it.

    IF ANY PROVEN BODY HAS DRIFTED, THIS FALLS BACK TO THE SCAN rather than continuing to cite a
    proof about source that no longer exists. Drift re-arms the brute force automatically; it never
    downgrades to trust.
    """
    intact, drifted = proof_binding_intact(pinned)
    if not intact:
        return assert_prefix_shape(entry, exit_state, ceiling, samples=samples)
    assert_reserves_possible(entry, "entry")
    assert_reserves_possible(exit_state, "exit")
    return True


def grid_row(entry, exit_state, quote_in, schedule, policy):
    """One preregistered size: is it payable, and what is left after the frozen costs.

    `net_after_costs_lamports` may be negative, and is reported rather than clamped. Clamping would
    hide the case that matters most on a small position.
    """
    assert_integer("quote_in", quote_in)
    payable = is_admissible(entry, exit_state, quote_in)
    row = {"quote_in_lamports": quote_in, "liquidity_executable": payable,
           "tokens_acquired": None, "gross_exit_lamports": None,
           "net_after_costs_lamports": None, "non_negative": None}
    if not payable:
        return row
    tokens = tokens_for(entry, quote_in)
    row["tokens_acquired"] = tokens
    entry_state = {**{k: entry[k] for k in ("virtual_quote", "virtual_token", "real_quote",
                                            "real_token", "quote_mint", "mayhem_mode", "complete")},
                   "slot": entry["context_slot"]}
    observed_exit = {**{k: exit_state[k] for k in ("virtual_quote", "virtual_token", "real_quote",
                                                   "real_token", "quote_mint", "mayhem_mode",
                                                   "complete")},
                     "slot": exit_state["context_slot"]}
    bought = B10A.price_entry(entry_state, {"side": B10A.BUY, "quote_lamports": quote_in},
                              schedule, policy)
    sold = B10A.price_exit(observed_exit, tokens, schedule, policy)
    if sold.get("status") != B10A.STATUS_PRICED:
        # The predicate said payable and B10a disagreed. That is a contradiction, not a refusal to
        # price, and it must stop the run rather than be recorded as an unexecutable size.
        raise CapacityRefused(
            f"{M_DIFFERENTIAL_DISAGREEMENT}: the predicate admitted {quote_in} but B10a returned "
            f"{sold.get('liquidity')}")
    row["gross_exit_lamports"] = sold["quote_lamports"]
    row["net_after_costs_lamports"] = (sold["lamports_into_wallet"]
                                       - bought["lamports_out_of_wallet"])
    row["non_negative"] = row["net_after_costs_lamports"] >= 0
    return row


def order_statistics(values):
    """Exact integer order statistics by index. No mean, no interpolation, no float."""
    if not values:
        return None
    ordered = sorted(values)

    def at(numerator, denominator):
        return ordered[(len(ordered) - 1) * numerator // denominator]

    return {"cells": len(ordered), "min": ordered[0], "p10": at(1, 10), "p25": at(1, 4),
            "median": at(1, 2), "p75": at(3, 4), "p90": at(9, 10), "max": ordered[-1]}


# --------------------------------------------------------------------------------------------
# The study
# --------------------------------------------------------------------------------------------

def run(document=None, entries=None, exits=None, schedules=None, tolerance=150,
        b15l_document=None, verify_differential=True):
    """Capacity per (horizon, delay); the grid per (scenario, horizon, delay). Never aggregated."""
    assert_no_execution_surface()
    document = verify_preregistration() if document is None else document
    frozen = document["frozen_inputs_unchanged"]
    ceiling = frozen["capacity_search_upper_bound_lamports"]
    delays, horizons = frozen["entry_delays_slots"], frozen["exit_horizons"]
    scenarios = frozen["cost_scenarios"]
    grid = document["secondary_estimand_separately_named"]["grid_lamports"]

    entries = B15L.load_entries() if entries is None else entries
    exits = B15L.load_exits() if exits is None else exits
    schedules = {} if schedules is None else schedules

    report = {"schema_version": SCHEMA_VERSION, "label": LABEL, "executable": False,
              "landing_probability": "unmeasured", "competitor_response": "unmeasured",
              "performance_status": "not_evaluated", "execution_status": "never_executed",
              "censoring_statement": CENSORING_STATEMENT,
              "search_ceiling_lamports": ceiling, "grid_lamports": grid,
              "capacity_by_horizon_delay": {}, "grid_by_scenario_horizon_delay": {},
              "refusals": {}}

    def refuse(code):
        report["refusals"][code] = report["refusals"].get(code, 0) + 1

    # Admissible cells, established ONCE by B15L's own gates so the two studies describe the same
    # rows. A cell B15L refuses is refused here with the same meaning.
    admissible = {}
    for key in sorted(exits):
        signature, delay, horizon = key
        if delay not in delays or horizon not in horizons:
            continue
        entry = entries.get((signature, delay))
        if entry is None or signature not in schedules:
            refuse(M_NOT_IN_B15L_UNIVERSE)
            continue
        exit_state = exits[key]
        try:
            B15L.assert_fresh(entry, tolerance, "entry")
            B15L.assert_fresh(exit_state, tolerance, "exit")
            B15L.assert_transportable(entry, exit_state)
        except B15L.CounterfactualRefused:
            refuse(M_NOT_IN_B15L_UNIVERSE)
            continue
        admissible[key] = (entry, exit_state)

    # Cells the CAPACITY loop refuses. Tracked because `continue` below leaves the key in
    # `admissible`, and the grid loop iterates that same dict -- so without this a cell refused for
    # impossible reserves was still PRICED by the grid, and the two loops described different sets
    # of cells while the report presented them as one study. It never fired on the burned run
    # (report.json carries zero capacity-loop refusals; the only refusals are
    # M_NOT_IN_B15L_UNIVERSE, which are recorded BEFORE a key enters `admissible`), and it could
    # not crash there either, because the crash needs quote_in == 1 exactly and every grid size is
    # at least 1,000,000. A guarantee by accident is not a guarantee.
    capacity_refused = set()

    for horizon in horizons:
        for delay in delays:
            capacities, zero, cap_hit, circular, floors = [], 0, 0, 0, []
            shortfall, shortfalls = 0, []
            for key in sorted(k for k in admissible if k[1] == delay and k[2] == horizon):
                entry, exit_state = admissible[key]
                try:
                    capacity = external_capacity(entry, exit_state, ceiling)
                    if verify_differential:
                        alternative = capacity_via_b10b(entry, exit_state, ceiling)
                        if alternative != capacity:
                            raise CapacityRefused(
                                f"{M_DIFFERENTIAL_DISAGREEMENT}: searching over the quote input "
                                f"gives {capacity} and B10b's token-side maximum gives "
                                f"{alternative}")
                except CapacityRefused as error:
                    refuse(str(error).split(":", 1)[0])
                    capacity_refused.add(key)
                    continue
                capacities.append(capacity)
                floor = minimum_effective_quote(entry, ceiling)
                if floor is not None:
                    floors.append(floor)
                if capacity == 0:
                    zero += 1
                    # Circular ONLY if B15L could price the exit while the external book could not
                    # pay for any positive buy at all. Counting every zero-capacity cell as
                    # circular would have conflated "no liquidity either way" with "liquidity our
                    # own purchase supplied", which are different findings.
                    if self_contributed_exit_payable(entry, exit_state, ceiling):
                        circular += 1
                if capacity == ceiling:
                    cap_hit += 1
                # Added AFTER the frozen circular condition was found to return zero on every
                # group, and labelled so a reader can weigh it accordingly. It measures what that
                # condition was reaching for: a cell B15L could price only because our own buy
                # supplied reserves the external book did not have.
                if capacity < ceiling and self_contributed_exit_payable(
                        entry, exit_state, ceiling):
                    shortfall += 1
                    shortfalls.append(ceiling - capacity)
            report["capacity_by_horizon_delay"][f"{horizon}|{delay}"] = {
                "label": LABEL, "cells": len(capacities),
                "external_liquidity_capacity_lamports": order_statistics(capacities),
                "zero_capacity_cells": zero,
                "cap_hit_cells": cap_hit,
                "cap_hit_note": ("a cap-hit capacity is at least the ceiling and was not measured "
                                 "further; it is never reported as equal to it"),
                "curve_resolution_floor_lamports": order_statistics(floors),
                "curve_resolution_floor_note": (
                    "the smallest input acquiring at least one token. The pinned exact-input "
                    "formula carries (q - 1) in its numerator, so a one-lamport buy acquires "
                    "nothing at any reserves. This is the curve's resolution, not a liquidity "
                    "limit, and the capacity search runs above it because the admissible set is "
                    "otherwise not a prefix"),
                CIRCULAR + "_cells": circular,
                CIRCULAR + "_note": ("the exit was payable only out of reserves our own purchase "
                                     "had added; an exit funded by one's own entry is not "
                                     "liquidity"),
                CIRCULAR + "_vacuous": ("the frozen condition requires an external capacity of "
                                        "exactly zero, and no cell in any group reached it: every "
                                        "book supported at least a few lamports. The condition is "
                                        "reported as measured, at zero, and the quantity below was "
                                        "added afterwards to measure what it was reaching for"),
                "self_funded_shortfall_cells": shortfall,
                "self_funded_shortfall_lamports": order_statistics(shortfalls),
                "self_funded_shortfall_note": (
                    "cells where B15L could price the exit but the EXTERNAL book could not support "
                    "the full frozen position, and by how many lamports it fell short. Defined "
                    "after seeing the frozen circular condition return zero, and labelled so that "
                    "is visible rather than buried"),
            }

    for scenario in scenarios:
        policy = {k: scenario[k] for k in ("base_fee_lamports", "priority_fee_lamports",
                                          "tip_lamports", "ata_rent_lamports", "failed_attempts")}
        for horizon in horizons:
            for delay in delays:
                per_size = {str(size): {"liquidity_executable_cells": 0, "cells": 0,
                                        "non_negative_cells": 0, "nets": []} for size in grid}
                for key in sorted(k for k in admissible
                                  if k[1] == delay and k[2] == horizon
                                  and k not in capacity_refused):
                    entry, exit_state = admissible[key]
                    for size in grid:
                        bucket = per_size[str(size)]
                        bucket["cells"] += 1
                        try:
                            row = grid_row(entry, exit_state, size, schedules[key[0]], policy)
                        except CapacityRefused as error:
                            refuse(str(error).split(":", 1)[0])
                            continue
                        if not row["liquidity_executable"]:
                            continue
                        bucket["liquidity_executable_cells"] += 1
                        bucket["nets"].append(row["net_after_costs_lamports"])
                        if row["non_negative"]:
                            bucket["non_negative_cells"] += 1
                summary = {}
                for size, bucket in per_size.items():
                    summary[size] = {
                        "cells": bucket["cells"],
                        "liquidity_executable_cells": bucket["liquidity_executable_cells"],
                        "non_negative_cells": bucket["non_negative_cells"],
                        "net_after_costs_lamports": order_statistics(bucket["nets"]),
                    }
                report["grid_by_scenario_horizon_delay"][
                    f"{scenario['scenario_id']}|{horizon}|{delay}"] = {
                        "label": LABEL, "by_size": summary,
                        "no_size_is_selected": "the grid is reported in full, including sizes that "
                                               "fail; nothing here ranks or recommends a size"}

    report["population"] = {"entry_checkpoints": len(entries), "exit_checkpoints": len(exits),
                            "fee_schedules": len(schedules), "admissible_cells": len(admissible)}
    assert_no_forbidden_words(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="B15m external liquidity capacity (offline, read-only, no network)")
    parser.add_argument("--out", default=None)
    parser.add_argument("--no-differential", action="store_true",
                        help="skip the B10b cross-check (not permitted for publication)")
    arguments = parser.parse_args(argv)
    entries = B15L.load_entries()
    exits = B15L.load_exits()
    schedules = B15L.fee_schedules({key[0] for key in exits})
    report = run(entries=entries, exits=exits, schedules=schedules,
                 verify_differential=not arguments.no_differential)
    text = json.dumps(report, indent=2, sort_keys=True)
    if arguments.out:
        target = pathlib.Path(arguments.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
