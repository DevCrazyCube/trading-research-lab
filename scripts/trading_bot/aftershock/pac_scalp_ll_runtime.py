#!/usr/bin/env python3
"""Credential-safe, pre-performance runtime contract for PAC_SCALP_LL.

The contract is written after latency evidence but before activation/performance.  It binds both
provider routes and every paper all-cost profile.  Full credentialed URLs never enter the artifact;
the process must reproduce the committed fingerprints from its in-memory environment.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import pathlib

from .execution import RefusedExecution
from . import pac_scalp_ll_campaign as campaigns
from . import pac_scalp_ll_route as routes


SCHEMA = 1
COST_NAMES = ("entry", "exit", "ata_close")
MIN_BASE_FEE_LAMPORTS = 5_000
MIN_PRIORITY_FEE_LAMPORTS = 500
MIN_TIP_LAMPORTS = 5_000


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _cost(value: object) -> routes.AttemptCost:
    if not isinstance(value, dict):
        raise RefusedExecution("PAC_SCALP_LL runtime cost is not an object")
    try:
        return routes.AttemptCost(**value)
    except (TypeError, RefusedExecution) as exc:
        raise RefusedExecution("PAC_SCALP_LL runtime cost is invalid") from exc


def build(*, campaign: campaigns.Campaign, attestation: dict,
          route_by_arm: dict[str, routes.Route],
          costs_by_arm: dict[str, dict[str, routes.AttemptCost]],
          provider_cost_receipt_sha256_by_arm: dict[str, str]) -> dict:
    if not isinstance(campaign, campaigns.Campaign) or set(route_by_arm) != routes.ARMS \
            or set(costs_by_arm) != routes.ARMS \
            or set(provider_cost_receipt_sha256_by_arm) != routes.ARMS:
        raise RefusedExecution("PAC_SCALP_LL runtime contract arms are incomplete")
    if (not isinstance(attestation, dict)
            or attestation.get("campaign_sha256") != campaign.campaign_sha256
            or attestation.get("evidence_status") != "FINALIZED_ATTESTED_COMPLETE"
            or not isinstance(attestation.get("attestation_sha256"), str)
            or _sha({k: v for k, v in attestation.items() if k != "attestation_sha256"})
            != attestation["attestation_sha256"]):
        raise RefusedExecution("PAC_SCALP_LL runtime lacks finalized fee authority")
    fees = attestation.get("meta_fee_lamports_by_arm")
    if not isinstance(fees, dict) or set(fees) != routes.ARMS:
        raise RefusedExecution("PAC_SCALP_LL runtime attested fee arms are incomplete")
    arms = {}
    for arm in sorted(routes.ARMS):
        route = route_by_arm[arm]
        costs = costs_by_arm[arm]
        if not isinstance(route, routes.Route) or route.arm != arm or set(costs) != set(COST_NAMES):
            raise RefusedExecution("PAC_SCALP_LL runtime route/cost binding is incomplete")
        expected_endpoint = (campaign.public_submit_endpoint_identity
                             if arm == routes.PUBLIC_CONTROL
                             else campaign.intervention_submit_endpoint_identity)
        expected_config = (campaign.public_submit_config_sha256
                           if arm == routes.PUBLIC_CONTROL
                           else campaign.intervention_submit_config_sha256)
        if (route.submit_endpoint_identity != expected_endpoint
                or campaigns.endpoint_config_sha256(route.submit_url) != expected_config):
            raise RefusedExecution("PAC_SCALP_LL runtime submit route differs from calibration")
        if any(not isinstance(costs[name], routes.AttemptCost) for name in COST_NAMES):
            raise RefusedExecution("PAC_SCALP_LL runtime lacks typed all-cost profiles")
        receipt = provider_cost_receipt_sha256_by_arm[arm]
        if (not isinstance(receipt, str) or len(receipt) != 64
                or any(char not in "0123456789abcdef" for char in receipt)):
            raise RefusedExecution("PAC_SCALP_LL runtime provider-cost receipt is invalid")
        if type(fees[arm]) is not int or fees[arm] <= 0 \
                or fees[arm] % campaign.samples_per_arm:
            raise RefusedExecution("PAC_SCALP_LL runtime attested fee aggregate is unusable")
        measured_fee = fees[arm] // campaign.samples_per_arm
        for name in COST_NAMES:
            cost = costs[name]
            if (cost.base_fee_lamports < MIN_BASE_FEE_LAMPORTS
                    or cost.priority_fee_lamports < MIN_PRIORITY_FEE_LAMPORTS
                    or cost.jito_tip_lamports < MIN_TIP_LAMPORTS
                    or cost.base_fee_lamports + cost.priority_fee_lamports < measured_fee):
                raise RefusedExecution("PAC_SCALP_LL runtime cost is below attested/frozen floor")
        if (arm == routes.LOW_LATENCY_INTERVENTION
                and costs["entry"].infra_subscription_num_lamports <= 0):
            raise RefusedExecution("PAC_SCALP_LL paid arm cannot erase subscription cost")
        arms[arm] = {
            "provider_id": route.provider_id, "region": route.region,
            "submit_endpoint_identity": route.submit_endpoint_identity,
            "observe_endpoint_identity": route.observe_endpoint_identity,
            "config_fingerprint_sha256": route.config_fingerprint_sha256,
            "provider_cost_receipt_sha256": receipt,
            "costs": {name: asdict(costs[name]) for name in COST_NAMES},
        }
    body = {"schema": SCHEMA, "instrument_id": campaigns.INSTRUMENT,
            "campaign_sha256": campaign.campaign_sha256, "arms": arms,
            "attestation_sha256": attestation["attestation_sha256"],
            "boundary": "PAPER_SCENARIO_ONLY_NO_SIGNER_NO_LIVE_ORDERS"}
    return {**body, "runtime_profile_sha256": _sha(body)}


def load(path: pathlib.Path, *, expected_file_sha256: str,
         campaign: campaigns.Campaign, attestation: dict) -> dict:
    try:
        payload = pathlib.Path(path).read_bytes(); row = json.loads(payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution("PAC_SCALP_LL runtime profile is unreadable") from exc
    if (not isinstance(attestation, dict)
            or attestation.get("campaign_sha256") != campaign.campaign_sha256
            or attestation.get("evidence_status") != "FINALIZED_ATTESTED_COMPLETE"
            or not isinstance(attestation.get("attestation_sha256"), str)
            or _sha({k: v for k, v in attestation.items() if k != "attestation_sha256"})
            != attestation["attestation_sha256"]):
        raise RefusedExecution("PAC_SCALP_LL runtime load lacks finalized fee authority")
    fees = attestation.get("meta_fee_lamports_by_arm")
    if not isinstance(fees, dict) or set(fees) != routes.ARMS:
        raise RefusedExecution("PAC_SCALP_LL runtime load fee arms are incomplete")
    if (not isinstance(expected_file_sha256, str)
            or hashlib.sha256(payload).hexdigest() != expected_file_sha256
            or not isinstance(row, dict)):
        raise RefusedExecution("PAC_SCALP_LL runtime profile file pin refuses")
    body = dict(row); observed = body.pop("runtime_profile_sha256", None)
    if (observed != _sha(body) or row.get("schema") != SCHEMA
            or row.get("instrument_id") != campaigns.INSTRUMENT
            or row.get("campaign_sha256") != campaign.campaign_sha256
            or row.get("attestation_sha256") != attestation["attestation_sha256"]
            or row.get("boundary") != "PAPER_SCENARIO_ONLY_NO_SIGNER_NO_LIVE_ORDERS"
            or set(row.get("arms", {})) != routes.ARMS):
        raise RefusedExecution("PAC_SCALP_LL runtime profile identity refuses")
    for arm, value in row["arms"].items():
        if (not isinstance(value, dict) or set(value) != {
                "provider_id", "region", "submit_endpoint_identity",
                "observe_endpoint_identity", "config_fingerprint_sha256",
                "provider_cost_receipt_sha256", "costs"}
                or not all(isinstance(value[name], str) and value[name] for name in (
                    "provider_id", "region", "submit_endpoint_identity",
                    "observe_endpoint_identity", "config_fingerprint_sha256"))
                or not isinstance(value["provider_cost_receipt_sha256"], str)
                or len(value["provider_cost_receipt_sha256"]) != 64
                or set(value["costs"]) != set(COST_NAMES)):
            raise RefusedExecution("PAC_SCALP_LL runtime arm schema refuses")
        for name in COST_NAMES:
            cost = _cost(value["costs"][name])
            if (type(fees[arm]) is not int or fees[arm] <= 0
                    or fees[arm] % campaign.samples_per_arm):
                raise RefusedExecution("PAC_SCALP_LL runtime attested fee aggregate is unusable")
            measured_fee = fees[arm] // campaign.samples_per_arm
            if (cost.base_fee_lamports < MIN_BASE_FEE_LAMPORTS
                    or cost.priority_fee_lamports < MIN_PRIORITY_FEE_LAMPORTS
                    or cost.jito_tip_lamports < MIN_TIP_LAMPORTS
                    or cost.base_fee_lamports + cost.priority_fee_lamports < measured_fee):
                raise RefusedExecution("PAC_SCALP_LL persisted cost falls below frozen floor")
        receipt = value["provider_cost_receipt_sha256"]
        if (len(receipt) != 64 or any(char not in "0123456789abcdef" for char in receipt)):
            raise RefusedExecution("PAC_SCALP_LL persisted provider-cost receipt is invalid")
        if (arm == routes.LOW_LATENCY_INTERVENTION
                and _cost(value["costs"]["entry"]).infra_subscription_num_lamports <= 0):
            raise RefusedExecution("PAC_SCALP_LL paid runtime cannot erase subscription cost")
    return row


def assert_environment(profile: dict, route_by_arm: dict[str, routes.Route]) -> None:
    if set(route_by_arm) != routes.ARMS:
        raise RefusedExecution("PAC_SCALP_LL runtime environment arms are incomplete")
    for arm in routes.ARMS:
        route, frozen = route_by_arm[arm], profile["arms"][arm]
        if (not isinstance(route, routes.Route) or route.arm != arm
                or route.provider_id != frozen["provider_id"] or route.region != frozen["region"]
                or route.submit_endpoint_identity != frozen["submit_endpoint_identity"]
                or route.observe_endpoint_identity != frozen["observe_endpoint_identity"]
                or route.config_fingerprint_sha256 != frozen["config_fingerprint_sha256"]):
            raise RefusedExecution("PAC_SCALP_LL runtime environment drift refuses")


def attempt_cost(profile: dict, arm: str, name: str) -> routes.AttemptCost:
    if arm not in routes.ARMS or name not in COST_NAMES:
        raise RefusedExecution("PAC_SCALP_LL runtime cost selector refuses")
    return _cost(profile["arms"][arm]["costs"][name])
