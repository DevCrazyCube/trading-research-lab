"""The client's guarantees are policy, so they are tested as policy. All offline.

"Public data only" and "bounded" are the two claims this whole build makes to anyone whose server
it touches. A claim that is only in a docstring is not a guarantee.
"""
from __future__ import annotations

import json

import pytest

from wbso.http_client import (
    API_HOSTS,
    BudgetExhausted,
    CredentialAttempt,
    PoliteClient,
)


@pytest.fixture
def client(tmp_path):
    return PoliteClient(
        cache_dir=tmp_path / "cache",
        budget=3,
        receipts_path=tmp_path / "receipts.jsonl",
        offline=True,
    )


@pytest.mark.parametrize(
    "header", ["Authorization", "authorization", "Cookie", "X-API-Key", "PRIVATE-TOKEN"]
)
def test_refuses_to_send_credential_headers(client, header):
    with pytest.raises(CredentialAttempt):
        client.get("https://api.github.com/orgs/x", headers={header: "secret"})


@pytest.mark.parametrize(
    "param", ["access_token", "api_key", "apiKey", "token", "client_secret"]
)
def test_refuses_credential_query_parameters(client, param):
    with pytest.raises(CredentialAttempt):
        client.get(f"https://api.github.com/orgs/x?{param}=secret")


def test_offline_without_cache_stops_rather_than_reaching_out(client):
    with pytest.raises(BudgetExhausted):
        client.get("https://api.github.com/orgs/x")


def test_cache_hit_serves_without_network(client, tmp_path):
    url = "https://api.github.com/orgs/example"
    path = client._cache_path(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"status": 200, "bytes": 12, "payload": {"login": "example"}}))
    status, payload = client.get(url)
    assert status == 200 and payload == {"login": "example"}
    assert client.spent == 0, "a cache hit must not consume the budget"
    assert client.receipts[-1].from_cache is True


def test_receipts_are_written_for_every_call(client, tmp_path):
    url = "https://api.github.com/orgs/example"
    client._cache_path(url).parent.mkdir(parents=True, exist_ok=True)
    client._cache_path(url).write_text(json.dumps({"status": 200, "bytes": 1, "payload": {}}))
    client.get(url, note="unit")
    lines = (tmp_path / "receipts.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["url"] == url and row["note"] == "unit" and row["at_utc"].endswith("Z")


def test_budget_is_a_hard_stop(tmp_path):
    c = PoliteClient(cache_dir=tmp_path / "c", budget=0)
    with pytest.raises(BudgetExhausted):
        c.get("https://api.github.com/orgs/x")


def test_documented_apis_skip_robots_but_websites_do_not(client):
    """robots.txt governs websites; the three public JSON APIs are used under their own terms."""
    assert client._robots_ok("https://api.github.com/orgs/x") is True
    assert "api.github.com" in API_HOSTS
    assert "directory.peppol.eu" in API_HOSTS
    assert "example.nl" not in API_HOSTS


def test_summary_counts_by_host(client):
    url = "https://api.github.com/orgs/example"
    client._cache_path(url).parent.mkdir(parents=True, exist_ok=True)
    client._cache_path(url).write_text(json.dumps({"status": 200, "bytes": 1, "payload": {}}))
    client.get(url)
    summary = client.summary()
    assert summary["by_host"]["api.github.com"] == 1
    assert summary["cache_hits"] == 1
    assert summary["requests_made"] == 0
