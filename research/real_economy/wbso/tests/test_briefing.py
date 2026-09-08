"""End-to-end briefing generation from a fixture candidate. Offline.

The guarantee worth testing hardest is the one a reader cannot check for themselves: that an
uncertain identity match — a KVK number obtained by matching a *name* in the Peppol Directory —
never reaches the recipient, no matter how convenient it would be to print it.
"""
from __future__ import annotations

import pathlib

import pytest

from wbso.briefing import (
    PLACEHOLDER_RE,
    estimate_developers,
    evidence_urls,
    generate,
    load_sender,
    nl_date,
    render_dossier,
)
from wbso.model import Candidate, Evidence
from wbso.params import load_params

ROOT = pathlib.Path(__file__).resolve().parent.parent
P = load_params()
SENDER = load_sender(ROOT / "params" / "sender_profile.example.json")
TODAY = "2026-08-19"

PEPPOL_MATCH = {
    "participant_id": "0106:14075247",
    "scheme": "0106",
    "identifier": "14075247",
    "is_kvk": True,
    "is_vat": False,
    "entity_name": "Voorbeeld",
    "country": "NL",
    "reg_date": "2020-01-01",
    "verify_before_use": True,
}


def candidate(**kw) -> Candidate:
    c = Candidate(
        candidate_id="gh:voorbeeld",
        display_name=kw.pop("display_name", "Voorbeeld Software"),
        github_login="voorbeeld",
        github_url="https://github.com/voorbeeld",
        website="https://voorbeeld.nl",
        public_email="info@voorbeeld.nl",
        location_text="Utrecht, Netherlands",
        public_repos=9,
        followers=12,
        github_created_at="2018-02-01T00:00:00Z",
        signals={
            "recent_repos_own": 3,
            "latest_push": "2026-08-15T00:00:00Z",
            "languages": ["Go", "TypeScript"],
            "enriched": True,
            "review_flags": [],
            **kw.pop("signals", {}),
        },
        score=70,
    )
    c.add(Evidence("github", "recent_public_repo",
                   "De publieke repository voorbeeld/tool (taal: Go) had een commit op 2026-08-15.",
                   "https://github.com/voorbeeld/tool", "2026-08-19T06:00:00Z", {}))
    for ev in kw.pop("evidence", []):
        c.add(ev)
    return c


def test_generated_briefing_lints_clean():
    text, dossier, lint = generate(candidate(), P, SENDER, today_iso=TODAY)
    assert lint.ok, lint.summary()
    assert dossier["lint"]["ok"] is True


def test_briefing_carries_the_rvo_numbers_and_both_deadlines():
    text, _, _ = generate(candidate(), P, SENDER, today_iso=TODAY)
    assert "36%" in text and "16%" in text and "50%" in text
    assert "391.020" in text and "15.979" in text
    assert nl_date(P.deadlines["voor_extra_aanvraag_okt_dec_2026"]) in text
    assert nl_date(P.deadlines["voor_ingangsdatum_1_januari_2027"]) in text
    assert "30 september 2026" in text and "20 december 2026" in text


def test_briefing_states_that_2027_parameters_are_not_yet_published():
    text, _, _ = generate(candidate(), P, SENDER, today_iso=TODAY)
    assert "2027" in text and "nog niet gepubliceerd" in text


def test_peppol_identifier_never_reaches_the_recipient():
    """A name match is not an identity. The KVK number stays in the owner's dossier."""
    ev = Evidence("peppol", "nl_entity_corroboration",
                  "In de openbare Peppol Directory staat ... geregistreerd voor e-facturatie.",
                  "https://directory.peppol.eu/participant/0106%3A14075247",
                  "2026-08-19T06:00:00Z", PEPPOL_MATCH)
    cand = candidate(signals={"peppol_match": PEPPOL_MATCH}, evidence=[ev])
    text, dossier, lint = generate(cand, P, SENDER, today_iso=TODAY)
    assert "14075247" not in text
    assert "0106" not in text
    assert "peppol" not in text.lower()
    assert lint.ok, lint.summary()
    assert any("14075247" in str(c) for c in dossier["owner_checklist"])


def test_dossier_marks_the_briefing_unsendable_while_the_sender_has_placeholders():
    dossier = render_dossier(candidate(), P, today_iso=TODAY)
    assert dossier["sendable"] is False and dossier["sent"] is False
    assert SENDER["_ready_to_send"] is False
    assert SENDER["_placeholders"], "the example sender profile must stay a template"


def test_every_generated_briefing_is_stamped_concept():
    text, _, _ = generate(candidate(), P, SENDER, today_iso=TODAY)
    assert "CONCEPT" in text and "NIET VERZENDEN" in text
    assert PLACEHOLDER_RE.search(text), "unfilled sender fields must remain visible, not silently blank"


@pytest.mark.parametrize(
    "signals,expected",
    [({}, 1), ({"careers_dev_terms": ["developer"]}, 2)],
)
def test_developer_estimate_starts_at_one_and_needs_a_second_signal(signals, expected):
    devs, reason = estimate_developers(candidate(signals=signals))
    assert devs == expected
    assert "repositor" in reason


def test_scenario_table_is_a_range_not_a_number():
    text, _, _ = generate(candidate(), P, SENDER, today_iso=TODAY)
    rows = [line for line in text.splitlines() if line.startswith("| ") and "€" in line]
    assert len(rows) >= 3, "a single euro figure reads as a promise; the ladder must survive"


def test_evidence_urls_include_sender_urls_from_placeholders():
    urls = evidence_urls(candidate(), SENDER)
    assert any("voorbeeld.nl" in u for u in urls)
