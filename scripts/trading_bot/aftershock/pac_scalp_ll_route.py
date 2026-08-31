#!/usr/bin/env python3
"""Default-OFF route contract for the matched public-vs-low-latency campaign.

This module contains no sender and no endpoint defaults.  It prevents a missing paid credential from
silently falling back to the public RPC while labelling the observation as an intervention.  Full
URLs exist only in process memory; persisted identities are scheme+host plus an operator-declared
provider and immutable region.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
import urllib.parse
import json

from .execution import RefusedExecution


PUBLIC_CONTROL = "PUBLIC_CONTROL"
LOW_LATENCY_INTERVENTION = "LOW_LATENCY_INTERVENTION"
ARMS = frozenset({PUBLIC_CONTROL, LOW_LATENCY_INTERVENTION})


def _endpoint_identity(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        raise RefusedExecution("route endpoint is not a credential-safe HTTP(S) URL")
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme}://{parsed.hostname.lower()}{port}"


def derived_config_fingerprint(*, provider_id: str, region: str,
                               submit_url: str, observe_url: str) -> str:
    """Credential-safe but mutation-sensitive route fingerprint.

    Full query values are hashed individually and never persisted.  Changing a path, credential,
    provider, or region necessarily changes the fingerprint without exposing the credential.
    """
    def safe(url: str) -> dict:
        parsed = urllib.parse.urlsplit(url)
        identity = _endpoint_identity(url)
        query = sorted((key, hashlib.sha256(value.encode()).hexdigest())
                       for key, value in urllib.parse.parse_qsl(
                           parsed.query, keep_blank_values=True))
        return {"identity": identity, "path": parsed.path or "/", "query_value_sha256": query}
    if not isinstance(provider_id, str) or not provider_id \
            or not isinstance(region, str) or not region:
        raise RefusedExecution("route provider/region is incomplete")
    body = {"provider_id": provider_id, "region": region,
            "submit": safe(submit_url), "observe": safe(observe_url)}
    return hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Route:
    arm: str
    provider_id: str
    region: str
    submit_url: str = field(repr=False)
    observe_url: str = field(repr=False)
    submit_endpoint_identity: str
    observe_endpoint_identity: str
    config_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.arm not in ARMS:
            raise RefusedExecution("route arm is invalid")
        if not all(isinstance(value, str) and value for value in (
                self.provider_id, self.region, self.submit_url, self.observe_url)):
            raise RefusedExecution("route identity/configuration is incomplete")
        if self.submit_endpoint_identity != _endpoint_identity(self.submit_url):
            raise RefusedExecution("route submit endpoint identity mismatch")
        if self.observe_endpoint_identity != _endpoint_identity(self.observe_url):
            raise RefusedExecution("route observe endpoint identity mismatch")
        if (not isinstance(self.config_fingerprint_sha256, str)
                or len(self.config_fingerprint_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.config_fingerprint_sha256)):
            raise RefusedExecution("route credential-safe configuration fingerprint is invalid")
        expected = derived_config_fingerprint(
            provider_id=self.provider_id, region=self.region,
            submit_url=self.submit_url, observe_url=self.observe_url)
        if self.config_fingerprint_sha256 != expected:
            raise RefusedExecution("route configuration fingerprint is operator-asserted/drifted")


@dataclass(frozen=True)
class AttemptCost:
    base_fee_lamports: int
    priority_fee_lamports: int
    jito_tip_lamports: int
    failed_attempt_fees_lamports: int
    infra_subscription_num_lamports: int
    infra_subscription_den_trades: int

    def __post_init__(self) -> None:
        for name in ("base_fee_lamports", "priority_fee_lamports", "jito_tip_lamports",
                     "failed_attempt_fees_lamports", "infra_subscription_num_lamports"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise RefusedExecution(f"route cost {name} is invalid")
        if type(self.infra_subscription_den_trades) is not int or self.infra_subscription_den_trades <= 0:
            raise RefusedExecution("route infra-cost allocation denominator is invalid")

    @property
    def onchain_lamports(self) -> int:
        return (self.base_fee_lamports + self.priority_fee_lamports + self.jito_tip_lamports
                + self.failed_attempt_fees_lamports)

    @property
    def allocated_infra_lamports(self) -> int:
        # Frozen conservative allocation: ceil(monthly/provider cost / preregistered trade count).
        return ((self.infra_subscription_num_lamports + self.infra_subscription_den_trades - 1)
                // self.infra_subscription_den_trades)

    @property
    def all_cost_lamports(self) -> int:
        return self.onchain_lamports + self.allocated_infra_lamports

    @property
    def attempt_cost_lamports(self) -> int:
        """Cost of this on-chain attempt; monthly infra is allocated exactly once at entry."""
        return self.onchain_lamports


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not isinstance(value, str) or not value.strip():
        raise RefusedExecution(f"required route environment variable {name} is absent")
    return value.strip()


def load_routes_from_env() -> tuple[Route, Route]:
    """Load both arms atomically.  There is intentionally no public fallback for the paid arm."""
    public_submit = _env("PAC_SCALP_LL_PUBLIC_SUBMIT_RPC_URL")
    public_observe = _env("PAC_SCALP_LL_PUBLIC_OBSERVE_RPC_URL")
    paid_submit = _env("PAC_SCALP_LL_INTERVENTION_SUBMIT_RPC_URL")
    paid_observe = _env("PAC_SCALP_LL_INTERVENTION_OBSERVE_RPC_URL")
    public_provider, public_region = (_env("PAC_SCALP_LL_PUBLIC_PROVIDER_ID"),
                                      _env("PAC_SCALP_LL_PUBLIC_REGION"))
    paid_provider, paid_region = (_env("PAC_SCALP_LL_INTERVENTION_PROVIDER_ID"),
                                  _env("PAC_SCALP_LL_INTERVENTION_REGION"))
    public = Route(
        PUBLIC_CONTROL, public_provider, public_region, public_submit, public_observe,
        _endpoint_identity(public_submit), _endpoint_identity(public_observe),
        _env("PAC_SCALP_LL_PUBLIC_CONFIG_FINGERPRINT_SHA256"))
    paid = Route(
        LOW_LATENCY_INTERVENTION, paid_provider, paid_region, paid_submit, paid_observe,
        _endpoint_identity(paid_submit), _endpoint_identity(paid_observe),
        _env("PAC_SCALP_LL_INTERVENTION_CONFIG_FINGERPRINT_SHA256"))
    if public.submit_endpoint_identity == paid.submit_endpoint_identity:
        raise RefusedExecution("matched campaign arms share a submit endpoint")
    if public.observe_endpoint_identity == paid.observe_endpoint_identity:
        raise RefusedExecution("matched campaign arms share an observe endpoint")
    return public, paid


def assigned_arm(campaign_sha256: str, pair_index: int, member_index: int) -> str:
    """Deterministic blocked randomization: every two-attempt block has one sample per arm."""
    if (not isinstance(campaign_sha256, str) or len(campaign_sha256) != 64
            or any(c not in "0123456789abcdef" for c in campaign_sha256)
            or type(pair_index) is not int or pair_index < 0
            or type(member_index) is not int or member_index not in {0, 1}):
        raise RefusedExecution("matched arm assignment inputs are invalid")
    flip = hashlib.sha256(f"{campaign_sha256}:{pair_index}".encode()).digest()[0] & 1
    intervention = member_index == flip
    return LOW_LATENCY_INTERVENTION if intervention else PUBLIC_CONTROL
