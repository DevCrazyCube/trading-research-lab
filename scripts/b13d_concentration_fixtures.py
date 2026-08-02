"""B13d fixture corpus and offline report — synthetic snapshots only. No RPC, no burned data.

Every balance below is invented. Nothing was queried, no node was contacted, the burned corpus was
not opened and B11a was never touched. The mints are called `MintAlpha…` precisely so nobody can
mistake this for a description of a real token.

The corpus exists to exercise the arithmetic and the refusals together: a curve holding most of the
supply so the two denominators disagree loudly, an owner holding several accounts so collapsing
changes the answer, an unresolved account that blocks collapsing entirely, a token with fewer
holders than k, a zero-balance account that must not vanish, and an incomplete enumeration with a
published residual.

The report publishes **structural counts and arithmetic agreement only**. It does not publish a
concentration value, a share, a distribution or a ranking: this pass exists to show the plumbing is
exact, and a number here would be read as a finding about a token that does not exist.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B13D = _load("b13d_concentration", "b13d_concentration.py")
B13C = B13D.B13C
B10B = B13D.B10B

MINT = "MintAlphaSyntheticNothingRealHere111111111"
OTHER_MINT = "MintBetaSyntheticNothingRealHere2222222222"
DECIMALS = 6
CREATOR = "OwnerCreatorSynthetic11111111111111111111"


def at(slot, index=0, outer=0, inner=0):
    return {"slot": slot, "transaction_index": index, "outer_index": outer, "inner_index": inner}


def account(name, units, role=B13D.ROLE_USER, owner=None, resolved=True, mint=MINT,
            decimals=DECIMALS):
    """One synthetic token account."""
    if resolved:
        owner = owner or f"Owner-of-{name}"
        return {"token_account": name, "mint": mint, "decimals": decimals, "owner": owner,
                "owner_status": B13D.OWNER_EXACT,
                "owner_evidence": "synthetic account record names its owner",
                "raw_units": units, "role": role,
                "role_evidence": f"synthetic role assignment for {name}"}
    return {"token_account": name, "mint": mint, "decimals": decimals, "owner": None,
            "owner_status": B13D.OWNER_UNRESOLVED, "owner_evidence": None,
            "raw_units": units, "role": role,
            "role_evidence": f"synthetic role assignment for {name}"}


def completeness(accounts, complete=True, detail="synthetic enumeration"):
    return {"enumeration_complete": complete,
            "enumeration_method": "synthetic full enumeration of a fixture set",
            "accounts_enumerated": len(accounts),
            "source_hashes": [hashlib.sha256(b"synthetic holder source").hexdigest()],
            "detail": detail}


def snapshot(name, accounts, supply, slot=430_000_000, complete=True, creator_binding=None):
    return B13D.build_snapshot(
        MINT, DECIMALS, at(slot), f"synthetic receipt provenance for {name}", accounts, supply,
        completeness(accounts, complete=complete),
        creator_binding=creator_binding,
        source_sha256=hashlib.sha256(name.encode()).hexdigest())


def exact_creator():
    return {"status": B13D.CREATOR_BINDING_EXACT, "address": CREATOR,
            "evidence": "the synthetic launch record names this address as creator"}


def build_fixture_corpus():
    """A deterministic synthetic corpus, one entry per seam worth exercising."""
    corpus = {}

    # 1. The curve holds most of the supply. Under total supply every user looks small; under the
    #    circulating-user denominator the same holdings are enormous. Both are true.
    accounts = [
        account("curve-account", 800_000_000, role=B13D.ROLE_BONDING_CURVE),
        account("holder-1", 120_000_000, owner=CREATOR),
        account("holder-2", 50_000_000),
        account("holder-3", 20_000_000),
        account("holder-4", 8_000_000),
        account("holder-5", 2_000_000),
    ]
    corpus["curve_dominant"] = snapshot("curve_dominant", accounts, 1_000_000_000,
                                        creator_binding=exact_creator())

    # 2. One owner holding four accounts. Collapsing changes the top-1 share, which is exactly why
    #    the two groupings are published separately and never merged by default.
    split = "OwnerSplitAcrossAccounts1111111111111111"
    accounts = [account(f"split-{i}", 100_000_000, owner=split) for i in range(4)]
    accounts += [account("single-1", 300_000_000), account("single-2", 200_000_000),
                 account("curve-account", 100_000_000, role=B13D.ROLE_BONDING_CURVE)]
    corpus["owner_split"] = snapshot("owner_split", accounts, 1_000_000_000)

    # 3. One unresolved account. Collapsing to owners is refused outright: that account could be
    #    the largest holder's, and a top-1 without it is a lower bound.
    accounts = [account("resolved-1", 400_000_000), account("resolved-2", 300_000_000),
                account("mystery", 300_000_000, resolved=False)]
    corpus["unresolved_owner"] = snapshot("unresolved_owner", accounts, 1_000_000_000)

    # 4. Fewer holders than k. A "top 10" over three accounts is the whole set, and the report has
    #    to say so or it will be compared against a genuine top 10 somewhere else.
    accounts = [account("only-1", 600_000_000), account("only-2", 300_000_000),
                account("only-3", 100_000_000)]
    corpus["fewer_than_k"] = snapshot("fewer_than_k", accounts, 1_000_000_000)

    # 5. A zero-balance account. It stays in the enumeration and out of the holder count.
    accounts = [account("live-1", 700_000_000), account("live-2", 300_000_000),
                account("emptied", 0)]
    corpus["zero_balance"] = snapshot("zero_balance", accounts, 1_000_000_000)

    # 6. Every non-user role at once, including unknown. Unknown is not a user and shrinks the
    #    circulating denominator rather than padding it.
    accounts = [
        account("user-1", 100_000_000),
        account("curve-account", 500_000_000, role=B13D.ROLE_BONDING_CURVE),
        account("vault-account", 200_000_000, role=B13D.ROLE_VAULT),
        account("burn-account", 100_000_000, role=B13D.ROLE_BURN),
        account("program-account", 60_000_000, role=B13D.ROLE_PROGRAM_OWNED),
        account("mystery-role", 40_000_000, role=B13D.ROLE_UNKNOWN),
    ]
    corpus["every_role"] = snapshot("every_role", accounts, 1_000_000_000)

    # 7. An incomplete enumeration with a published residual. Legitimate, and it may not claim to
    #    be complete.
    accounts = [account("partial-1", 400_000_000), account("partial-2", 100_000_000)]
    corpus["incomplete"] = snapshot("incomplete", accounts, 1_000_000_000, complete=False)

    # 8. All supply held by the curve: the circulating-user denominator is zero, and a share of it
    #    is UNDEFINED rather than zero.
    accounts = [account("curve-account", 1_000_000_000, role=B13D.ROLE_BONDING_CURVE)]
    corpus["no_circulating"] = snapshot("no_circulating", accounts, 1_000_000_000)

    # 9. A later snapshot of the same mint, for the point-in-time selection check.
    accounts = [account("later-1", 900_000_000), account("later-2", 100_000_000)]
    corpus["later_state"] = snapshot("later_state", accounts, 1_000_000_000, slot=430_009_999)

    return corpus


DECISION_SLOTS = (430_000_000, 430_000_001, 430_005_000)


def check():
    """Structural integrity and arithmetic agreement only. No concentration value is published."""
    corpus = build_fixture_corpus()
    report = {
        "schema_version": B13D.SCHEMA_VERSION,
        "point_in_time_rule": B13D.POINT_IN_TIME_RULE,
        "denominator_rule": B13D.DENOMINATOR_RULE,
        "rpc_queried": False,
        "burned_corpus_touched": False,
        "b11a_touched": False,
        "snapshots": len(corpus),
        "accounts_total": 0,
        "snapshots_reconciled": 0,
        "concentrations_computed": 0,
        "both_denominators_published": 0,
        "shares_are_exact_rationals": 0,
        "top_k_monotone": 0,
        "roles_account_for_every_unit": 0,
        "owner_grouping_available_count": 0,
        "owner_grouping_refused_count": 0,
        "owner_and_account_groupings_differ": 0,
        "zero_balance_accounts_preserved": 0,
        "undefined_denominator_not_reported_as_zero": 0,
        "residual_published": 0,
        "hashes_stable": 0,
        "order_independent": 0,
        "future_snapshot_refused": 0,
        "point_in_time_selections": 0,
        "cluster_adjustment_refused": False,
        "association_ledger_rejected_as_cluster_map": False,
        "connected_components_refused": False,
        "concentration_values_reported": False,
        "concentration_values_reported_reason":
            "this pass shows the arithmetic is exact; a share published here would be read as a "
            "finding about a token that does not exist, and the thresholds it would be compared "
            "against have deliberately not been chosen",
        "thresholds_chosen": [],
        "errors": [],
    }

    for name, snap in sorted(corpus.items()):
        report["accounts_total"] += len(snap["accounts"])
        try:
            B13D.assert_snapshot(snap)
            report["snapshots_reconciled"] += 1
        except B10B.FreezeViolation as error:
            report["errors"].append({"snapshot": name, "error": str(error)[:200]})
            continue
        if B13D.snapshot_hash(snap) == snap["snapshot_sha256"]:
            report["hashes_stable"] += 1
        else:
            report["errors"].append({"snapshot": name, "error": "snapshot hash drift"})

        try:
            record = B13D.compute_concentration(snap)
        except B10B.FreezeViolation as error:
            report["errors"].append({"snapshot": name, "error": str(error)[:200]})
            continue
        report["concentrations_computed"] += 1

        published = set(record["shares"]["by_account"]) | set(record["shares"]["by_owner"])
        if published == set(B13D.DENOMINATORS):
            report["both_denominators_published"] += 1
        else:
            report["errors"].append({"snapshot": name, "error": "a denominator went unpublished"})

        exact, monotone = True, True
        for grouping in ("by_account", "by_owner"):
            for block in record["shares"][grouping].values():
                if not block.get("defined"):
                    continue
                for k in B13D.TOP_K:
                    share = block[f"top_{k}"]["share"]
                    if not isinstance(share["numerator"], int) \
                            or not isinstance(share["denominator"], int):
                        exact = False
                if B13D.compare_rationals(block["top_1"]["share"], block["top_10"]["share"]) > 0:
                    monotone = False
        report["shares_are_exact_rationals"] += int(exact)
        report["top_k_monotone"] += int(monotone)
        if not exact:
            report["errors"].append({"snapshot": name, "error": "a share was not an exact rational"})
        if not monotone:
            report["errors"].append({"snapshot": name, "error": "top-k is not monotone"})

        role_units = sum(block["units"] for block in record["by_role"].values())
        if role_units == record["accounting"]["units_held_in_accounts"]:
            report["roles_account_for_every_unit"] += 1
        else:
            report["errors"].append({"snapshot": name, "error": "roles do not account for the "
                                                                "units"})

        if record["accounting"]["owner_grouping_available"]:
            report["owner_grouping_available_count"] += 1
            account_top = record["shares"]["by_account"][B13D.DENOMINATOR_TOTAL_SUPPLY]["top_1"]
            owner_top = record["shares"]["by_owner"][B13D.DENOMINATOR_TOTAL_SUPPLY]["top_1"]
            if B13D.compare_rationals(owner_top["share"], account_top["share"]) > 0:
                report["owner_and_account_groupings_differ"] += 1
        else:
            report["owner_grouping_refused_count"] += 1

        if record["accounting"]["zero_balance_account_count_observed"] > 0:
            if (record["accounting"]["accounts_with_positive_balance"]
                    < record["accounting"]["accounts_enumerated"]):
                report["zero_balance_accounts_preserved"] += 1
            else:
                report["errors"].append({"snapshot": name, "error": "a zero-balance account "
                                                                    "vanished"})

        circulating = record["shares"]["by_account"][B13D.DENOMINATOR_CIRCULATING_USER]
        if not circulating.get("defined"):
            if "undefined_reason" in circulating and "top_1" not in circulating:
                report["undefined_denominator_not_reported_as_zero"] += 1
            else:
                report["errors"].append({"snapshot": name,
                                         "error": "an undefined share was reported as a number"})
        if record["accounting"]["supply_residual_units"] > 0:
            if not record["accounting"]["enumeration_complete"]:
                report["residual_published"] += 1
            else:
                report["errors"].append({"snapshot": name,
                                         "error": "a complete enumeration published a residual"})

        shuffled = dict(snap, accounts=list(reversed(snap["accounts"])))
        shuffled["snapshot_sha256"] = B13D.snapshot_hash(shuffled)
        if (B13D.compute_concentration(shuffled)["shares"]
                == record["shares"]):
            report["order_independent"] += 1
        else:
            report["errors"].append({"snapshot": name, "error": "order dependent"})

    # Point in time: a later snapshot may never inform an earlier decision.
    everything = list(corpus.values())
    later = corpus["later_state"]
    for slot in DECISION_SLOTS:
        report["point_in_time_selections"] += 1
        t0 = at(slot)
        if B13D.available_at(later, t0) == (slot >= 430_009_999):
            report["future_snapshot_refused"] += 1
        else:
            report["errors"].append({"slot": slot, "error": "a later snapshot was admitted"})
        selected = B13D.select_snapshot(everything, t0)
        if not B13D.is_absent(selected) and not B13D.available_at(selected, t0):
            report["errors"].append({"slot": slot, "error": "selection returned a future snapshot"})

    try:
        B13D.cluster_adjusted_concentration(corpus["curve_dominant"], {"anything": True})
        report["errors"].append({"error": "a cluster-adjusted figure was produced"})
    except B13D.ClusterAdjustmentRefused:
        report["cluster_adjustment_refused"] = True

    # A B13b ledger passed as a cluster map must get its own refusal, naming what it actually is.
    ledger_shaped = {"confidence_status": "uncalibrated_evidence_only", "links": [],
                     "evidence_hash_chain_sha256": "0" * 64}
    try:
        B13D.cluster_adjusted_concentration(corpus["curve_dominant"], ledger_shaped)
        report["errors"].append({"error": "an association ledger was accepted as a cluster map"})
    except B13D.ClusterAdjustmentRefused as error:
        report["association_ledger_rejected_as_cluster_map"] = "ASSOCIATION EVIDENCE" in str(error)
        if not report["association_ledger_rejected_as_cluster_map"]:
            report["errors"].append({"error": "an association ledger was refused generically, so "
                                               "nobody is told what they actually passed"})
    try:
        B13D.connected_components(everything)
        report["errors"].append({"error": "a connected component was produced"})
    except B13D.ClusterAdjustmentRefused:
        report["connected_components_refused"] = True

    digest = hashlib.sha256()
    for name, snap in sorted(corpus.items()):
        digest.update(B13D.compute_concentration(snap)["concentration_sha256"].encode())
    report["determinism"] = {"concentrations_hashed": len(corpus),
                             "concentration_hash_chain_sha256": digest.hexdigest()}
    return report


def gate_failures(report):
    """Why this run does not pass the gate. Pure, so the gate's own logic can be tested."""
    failures = []
    if report["errors"]:
        failures.append(f"{len(report['errors'])} integrity errors: {report['errors'][:5]}")
    total = report["snapshots"]
    for field in ("snapshots_reconciled", "concentrations_computed", "both_denominators_published",
                  "shares_are_exact_rationals", "top_k_monotone", "roles_account_for_every_unit",
                  "hashes_stable", "order_independent"):
        if report[field] != total:
            failures.append(f"{field} held for only {report[field]} of {total} snapshots")
    if report["future_snapshot_refused"] != report["point_in_time_selections"]:
        failures.append("a later holder state was admitted into an earlier decision")
    if not report["owner_grouping_refused_count"]:
        failures.append("no fixture exercised the refusal to collapse accounts to owners")
    if not report["zero_balance_accounts_preserved"]:
        failures.append("no fixture exercised zero-balance preservation")
    if not report["undefined_denominator_not_reported_as_zero"]:
        failures.append("no fixture exercised an undefined denominator")
    if not report["residual_published"]:
        failures.append("no fixture exercised a published supply residual")
    for field in ("cluster_adjustment_refused", "association_ledger_rejected_as_cluster_map",
                  "connected_components_refused"):
        if not report[field]:
            failures.append(f"{field} did not hold")
    if report["concentration_values_reported"]:
        failures.append("this gate may not publish a concentration value")
    if report["thresholds_chosen"]:
        failures.append("this pass chooses no threshold")
    if report["rpc_queried"] or report["burned_corpus_touched"] or report["b11a_touched"]:
        failures.append("this pass queries nothing and opens neither the burned corpus nor B11a")
    return failures


def assert_clean():
    report = check()
    failures = gate_failures(report)
    if failures:
        raise B13D.ConcentrationRefused("; ".join(failures))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args(argv)
    report = assert_clean() if args.gate else check()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"ConcentrationRefused: {error}", file=sys.stderr)
        sys.exit(2)
