#!/usr/bin/env python3
"""Frozen matched submit-latency campaign contract for PAC_SCALP_LL.

Raw transaction evidence stays local because signatures expose the calibration wallet.  Commit-safe
campaign/summary artifacts contain only credential-safe endpoint identities, a SHA-256 payer
fingerprint, aggregate clocks, and hashes of the local raw evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import pathlib
import urllib.parse

from .execution import RefusedExecution
from . import pac_scalp_ll_route as routes
from . import pac_scalp_ll_tx as tx


INSTRUMENT = "AFTERSHOCK_PAC_SCALP_LL"
SCHEMA = 2
MIN_SAMPLES_PER_ARM = 100
POLL_INTERVAL_NANOS = 100_000_000
LANDING_DEADLINE_NANOS = 30_000_000_000
EVIDENCE_MODE = "FIRST_PROCESSED_STATUS_NEUTRAL_OBSERVER_PLUS_FINALIZED_ATTESTATION"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def _is_sha(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def endpoint_identity(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RefusedExecution("calibration endpoint is not credential-safe HTTPS")
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"https://{parsed.hostname.lower()}{port}"


def endpoint_config_sha256(url: str) -> str:
    """Return a credential-safe, mutation-sensitive pin for one runtime URL."""
    parsed = urllib.parse.urlsplit(url)
    identity = endpoint_identity(url)
    query = sorted((key, hashlib.sha256(value.encode()).hexdigest())
                   for key, value in urllib.parse.parse_qsl(
                       parsed.query, keep_blank_values=True))
    return sha({"identity": identity, "path": parsed.path or "/",
                "query_value_sha256": query})


@dataclass(frozen=True)
class Campaign:
    campaign_sha256: str
    created_unix_nanos: int
    fee_payer_fingerprint_sha256: str
    public_submit_endpoint_identity: str
    public_submit_config_sha256: str
    intervention_submit_endpoint_identity: str
    intervention_submit_config_sha256: str
    verification_endpoint_identity: str
    verification_config_sha256: str
    samples_per_arm: int
    max_lamports: int
    profile: tx.Profile


def build(*, created_unix_nanos: int, fee_payer_fingerprint_sha256: str,
          public_submit_url: str, intervention_submit_url: str, verification_url: str,
          samples_per_arm: int, max_lamports: int, profile: tx.Profile) -> dict:
    if (type(created_unix_nanos) is not int or created_unix_nanos <= 0
            or not _is_sha(fee_payer_fingerprint_sha256)
            or type(samples_per_arm) is not int or samples_per_arm < MIN_SAMPLES_PER_ARM
            or type(max_lamports) is not int or max_lamports <= 0
            or not isinstance(profile, tx.Profile)):
        raise RefusedExecution("low-latency campaign inputs are invalid")
    public_identity = endpoint_identity(public_submit_url)
    intervention_identity = endpoint_identity(intervention_submit_url)
    verification_identity = endpoint_identity(verification_url)
    if len({public_identity, intervention_identity, verification_identity}) != 3:
        raise RefusedExecution("campaign submit arms and neutral observer are not isolated")
    body = {
        "schema": SCHEMA, "instrument_id": INSTRUMENT,
        "created_unix_nanos": created_unix_nanos,
        "fee_payer_fingerprint_sha256": fee_payer_fingerprint_sha256,
        "public_submit_endpoint_identity": public_identity,
        "public_submit_config_sha256": endpoint_config_sha256(public_submit_url),
        "intervention_submit_endpoint_identity": intervention_identity,
        "intervention_submit_config_sha256": endpoint_config_sha256(intervention_submit_url),
        "verification_endpoint_identity": verification_identity,
        "verification_config_sha256": endpoint_config_sha256(verification_url),
        "samples_per_arm": samples_per_arm, "max_lamports": max_lamports,
        "poll_interval_nanos": POLL_INTERVAL_NANOS,
        "landing_deadline_nanos": LANDING_DEADLINE_NANOS,
        "evidence_mode": EVIDENCE_MODE, "transaction_profile": tx.PROFILE,
        "compute_unit_limit": profile.compute_unit_limit,
        "micro_lamports_per_cu": profile.micro_lamports_per_cu,
        "tip_lamports": profile.tip_lamports, "tip_account": profile.tip_account,
        "matched_block_randomization": "SHA256_CAMPAIGN_PAIR_ONE_PER_ARM",
        "shape_boundary": "NO_PUMP_ACCOUNTS_NO_TRADE_LOWER_BOUND_NOT_LIVE_CONTENTION",
    }
    return {**body, "campaign_sha256": sha(body)}


def load(path: pathlib.Path, *, expected_sha256: str) -> Campaign:
    path = pathlib.Path(path)
    try:
        payload = path.read_bytes(); row = json.loads(payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution("low-latency campaign is unreadable") from exc
    if not _is_sha(expected_sha256) or hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise RefusedExecution("low-latency campaign differs from external file pin")
    if not isinstance(row, dict):
        raise RefusedExecution("low-latency campaign is not an object")
    expected_keys = {
        "schema", "instrument_id", "created_unix_nanos", "fee_payer_fingerprint_sha256",
        "public_submit_endpoint_identity", "public_submit_config_sha256",
        "intervention_submit_endpoint_identity", "intervention_submit_config_sha256",
        "verification_endpoint_identity", "verification_config_sha256", "samples_per_arm",
        "max_lamports", "poll_interval_nanos", "landing_deadline_nanos", "evidence_mode",
        "transaction_profile", "compute_unit_limit", "micro_lamports_per_cu",
        "tip_lamports", "tip_account", "matched_block_randomization", "shape_boundary",
        "campaign_sha256",
    }
    sha_fields = ("fee_payer_fingerprint_sha256", "public_submit_config_sha256",
                  "intervention_submit_config_sha256", "verification_config_sha256")
    identities = tuple(row.get(key) for key in (
        "public_submit_endpoint_identity", "intervention_submit_endpoint_identity",
        "verification_endpoint_identity"))
    try:
        profile = tx.Profile(row.get("compute_unit_limit"), row.get("micro_lamports_per_cu"),
                             row.get("tip_lamports"), row.get("tip_account"))
    except (TypeError, RefusedExecution) as exc:
        raise RefusedExecution("low-latency campaign transaction profile is invalid") from exc
    if (set(row) != expected_keys or row.get("schema") != SCHEMA
            or row.get("instrument_id") != INSTRUMENT
            or type(row.get("created_unix_nanos")) is not int
            or row["created_unix_nanos"] <= 0
            or any(not _is_sha(row.get(key)) for key in sha_fields)
            or any(not isinstance(value, str) or not value.startswith("https://")
                   for value in identities)
            or len(set(identities)) != 3
            or type(row.get("samples_per_arm")) is not int
            or row["samples_per_arm"] < MIN_SAMPLES_PER_ARM
            or type(row.get("max_lamports")) is not int or row["max_lamports"] <= 0
            or row.get("poll_interval_nanos") != POLL_INTERVAL_NANOS
            or row.get("landing_deadline_nanos") != LANDING_DEADLINE_NANOS
            or row.get("evidence_mode") != EVIDENCE_MODE
            or row.get("transaction_profile") != tx.PROFILE
            or row.get("matched_block_randomization") != "SHA256_CAMPAIGN_PAIR_ONE_PER_ARM"
            or row.get("shape_boundary")
            != "NO_PUMP_ACCOUNTS_NO_TRADE_LOWER_BOUND_NOT_LIVE_CONTENTION"
            or row.get("campaign_sha256") != sha({
                key: value for key, value in row.items() if key != "campaign_sha256"})):
        raise RefusedExecution("low-latency campaign schema/content id mismatch")
    return Campaign(
        row["campaign_sha256"], row["created_unix_nanos"],
        row["fee_payer_fingerprint_sha256"], row["public_submit_endpoint_identity"],
        row["public_submit_config_sha256"], row["intervention_submit_endpoint_identity"],
        row["intervention_submit_config_sha256"], row["verification_endpoint_identity"],
        row["verification_config_sha256"],
        row["samples_per_arm"], row["max_lamports"],
        profile)


def assert_runtime_urls(campaign: Campaign, *, public_submit_url: str,
                        intervention_submit_url: str, verification_url: str) -> None:
    """Fail closed if in-memory URLs differ from the committed credential-safe pins."""
    if not isinstance(campaign, Campaign):
        raise RefusedExecution("runtime campaign is not typed")
    actual = (
        (endpoint_identity(public_submit_url), endpoint_config_sha256(public_submit_url)),
        (endpoint_identity(intervention_submit_url),
         endpoint_config_sha256(intervention_submit_url)),
        (endpoint_identity(verification_url), endpoint_config_sha256(verification_url)),
    )
    expected = (
        (campaign.public_submit_endpoint_identity, campaign.public_submit_config_sha256),
        (campaign.intervention_submit_endpoint_identity,
         campaign.intervention_submit_config_sha256),
        (campaign.verification_endpoint_identity, campaign.verification_config_sha256),
    )
    if actual != expected:
        raise RefusedExecution("runtime campaign endpoint/credential drift")


def arm_for(campaign_sha256: str, attempt_index: int) -> str:
    if type(attempt_index) is not int or attempt_index < 0:
        raise RefusedExecution("campaign attempt index is invalid")
    return routes.assigned_arm(campaign_sha256, attempt_index // 2, attempt_index % 2)
