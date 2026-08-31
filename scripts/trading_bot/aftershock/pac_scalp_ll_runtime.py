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


def build(*, campaign: campaigns.Campaign, route_by_arm: dict[str, routes.Route],
          costs_by_arm: dict[str, dict[str, routes.AttemptCost]]) -> dict:
    if not isinstance(campaign, campaigns.Campaign) or set(route_by_arm) != routes.ARMS \
            or set(costs_by_arm) != routes.ARMS:
        raise RefusedExecution("PAC_SCALP_LL runtime contract arms are incomplete")
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
        arms[arm] = {
            "provider_id": route.provider_id, "region": route.region,
            "submit_endpoint_identity": route.submit_endpoint_identity,
            "observe_endpoint_identity": route.observe_endpoint_identity,
            "config_fingerprint_sha256": route.config_fingerprint_sha256,
            "costs": {name: asdict(costs[name]) for name in COST_NAMES},
        }
    body = {"schema": SCHEMA, "instrument_id": campaigns.INSTRUMENT,
            "campaign_sha256": campaign.campaign_sha256, "arms": arms,
            "boundary": "PAPER_SCENARIO_ONLY_NO_SIGNER_NO_LIVE_ORDERS"}
    return {**body, "runtime_profile_sha256": _sha(body)}


def load(path: pathlib.Path, *, expected_file_sha256: str,
         campaign: campaigns.Campaign) -> dict:
    try:
        payload = pathlib.Path(path).read_bytes(); row = json.loads(payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution("PAC_SCALP_LL runtime profile is unreadable") from exc
    if (not isinstance(expected_file_sha256, str)
            or hashlib.sha256(payload).hexdigest() != expected_file_sha256
            or not isinstance(row, dict)):
        raise RefusedExecution("PAC_SCALP_LL runtime profile file pin refuses")
    body = dict(row); observed = body.pop("runtime_profile_sha256", None)
    if (observed != _sha(body) or row.get("schema") != SCHEMA
            or row.get("instrument_id") != campaigns.INSTRUMENT
            or row.get("campaign_sha256") != campaign.campaign_sha256
            or row.get("boundary") != "PAPER_SCENARIO_ONLY_NO_SIGNER_NO_LIVE_ORDERS"
            or set(row.get("arms", {})) != routes.ARMS):
        raise RefusedExecution("PAC_SCALP_LL runtime profile identity refuses")
    for arm, value in row["arms"].items():
        if (not isinstance(value, dict) or set(value) != {
                "provider_id", "region", "submit_endpoint_identity",
                "observe_endpoint_identity", "config_fingerprint_sha256", "costs"}
                or not all(isinstance(value[name], str) and value[name] for name in (
                    "provider_id", "region", "submit_endpoint_identity",
                    "observe_endpoint_identity", "config_fingerprint_sha256"))
                or set(value["costs"]) != set(COST_NAMES)):
            raise RefusedExecution("PAC_SCALP_LL runtime arm schema refuses")
        for name in COST_NAMES:
            _cost(value["costs"][name])
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
