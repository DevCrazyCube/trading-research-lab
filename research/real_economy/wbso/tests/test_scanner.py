"""Scanner rules, against fixtures. No network, no live GitHub.

The interesting cases are all rejections: T26 §8 predicted the population proxy fails because large
foreign organisations appear under Dutch locations, so the exclusion rules are what actually decide
whether this pipeline is worth anything.
"""
from __future__ import annotations

import pytest

from wbso.model import Candidate
from wbso.scanner import (
    ScanConfig,
    academic_host,
    apply_exclusions,
    looks_public_body,
    score_candidate,
)
from wbso.sources import github_orgs as gh
from wbso.sources import peppol

CFG = ScanConfig(pushed_since="2026-02-01")
TODAY = "2026-08-19"


def make(**kw) -> Candidate:
    base = dict(
        candidate_id="gh:example",
        display_name="Example BV",
        github_login="example",
        github_url="https://github.com/example",
        website="https://example.nl",
        public_email="info@example.nl",
        location_text="Utrecht, Netherlands",
        public_repos=12,
        followers=30,
        github_created_at="2019-04-01T00:00:00Z",
    )
    signals = {"recent_repos_own": 3, "latest_push": "2026-08-10T10:00:00Z",
               "languages": ["Go", "Python"], "enriched": True}
    signals.update(kw.pop("signals", {}))
    base.update(kw)
    return Candidate(signals=signals, **base)


# --- repo evidence -------------------------------------------------------------------------


def test_forks_and_archived_repos_are_not_development_evidence():
    cand = make(signals={})
    repos = [
        {"full_name": "example/own", "html_url": "https://github.com/example/own", "fork": False,
         "archived": False, "pushed_at": "2026-08-01T00:00:00Z", "language": "Go"},
        {"full_name": "example/forked", "html_url": "https://github.com/example/forked", "fork": True,
         "archived": False, "pushed_at": "2026-08-02T00:00:00Z", "language": "Go"},
        {"full_name": "example/old", "html_url": "https://github.com/example/old", "fork": False,
         "archived": True, "pushed_at": "2026-08-03T00:00:00Z", "language": "C"},
    ]
    gh.attach_repo_evidence(cand, repos, pushed_since="2026-02-01")
    assert cand.signals["recent_repos_own"] == 1
    assert cand.signals["recent_repos_forks"] == 1
    assert [e.detail["full_name"] for e in cand.evidence_of("recent_public_repo")] == ["example/own"]


def test_every_evidence_row_has_a_url():
    cand = make(signals={})
    gh.attach_repo_evidence(
        cand,
        [{"full_name": "example/x", "html_url": "", "fork": False, "archived": False,
          "pushed_at": "2026-08-01T00:00:00Z"}],
        pushed_since="2026-02-01",
    )
    assert cand.evidence == []
    assert cand.signals["repos_without_url"] == 1


# --- location ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "location,dutch",
    [
        ("Amsterdam, The Netherlands", True),
        ("Nederland", True),
        ("Delft", True),
        ("NL", True),
        ("Berlin, Germany", False),
        ("", False),
        (None, False),
    ],
)
def test_location_verdict(location, dutch):
    assert gh.location_verdict(location)[0] is dutch


def test_multinational_location_raises_doubt():
    dutch, doubts = gh.location_verdict("Amsterdam, Netherlands / San Francisco, USA")
    assert dutch is True
    assert doubts, "an office in both places is not an NL SME"


def test_nl_token_does_not_match_inside_another_word():
    assert gh.location_verdict("Nashville")[0] is False


# --- exclusions ----------------------------------------------------------------------------


def test_clean_candidate_is_kept():
    cand = make()
    apply_exclusions(cand, CFG)
    assert cand.exclusions == []


def test_no_recent_own_repo_is_excluded():
    cand = make(signals={"recent_repos_own": 0})
    apply_exclusions(cand, CFG)
    assert any("niet-geforkte" in r for r in cand.exclusions)


def test_public_knowledge_institution_is_excluded_by_rvo_rule():
    for name in ("TU Delft University", "Hogeschool Rotterdam", "Gemeente Amsterdam", "UMC Utrecht"):
        cand = make(display_name=name)
        apply_exclusions(cand, CFG)
        assert any("publieke" in r for r in cand.exclusions), name


def test_public_body_detector_does_not_fire_on_ordinary_names():
    assert looks_public_body("Acme Software BV", "acme", "Utrecht, Netherlands", None) is None


def test_too_large_is_excluded():
    cand = make(public_repos=900)
    apply_exclusions(cand, CFG)
    assert any("te groot" in r for r in cand.exclusions)

    cand = make(followers=50_000)
    apply_exclusions(cand, CFG)
    assert any("te bekend" in r for r in cand.exclusions)


def test_non_nl_without_peppol_is_excluded_but_peppol_rescues():
    cand = make(location_text="Paris, France")
    apply_exclusions(cand, CFG)
    assert any("Nederlandse vestiging" in r for r in cand.exclusions)

    cand = make(location_text=None, signals={"recent_repos_own": 2, "enriched": True, "peppol_match": {"is_kvk": True}})
    apply_exclusions(cand, CFG)
    assert not any("Nederlandse vestiging" in r for r in cand.exclusions)


def test_unenriched_candidate_reports_that_and_nothing_else():
    """A candidate whose profile was never fetched must not be reported as 'has no website'."""
    cand = make(website=None, public_email=None, location_text=None,
                signals={"recent_repos_own": 2, "enriched": False})
    apply_exclusions(cand, CFG)
    assert cand.exclusions == [
        "niet verrijkt: buiten het verrijkingsbudget van deze run (geen profielgegevens opgehaald)"
    ]


def test_failed_screen_is_the_only_reason_given():
    cand = make(signals={"recent_repos_own": 0})
    apply_exclusions(cand, CFG)
    assert len(cand.exclusions) == 1 and "niet-geforkte" in cand.exclusions[0]


def test_no_contact_channel_is_excluded():
    cand = make(website=None, public_email=None)
    apply_exclusions(cand, CFG)
    assert any("contactkanaal" in r for r in cand.exclusions)


# --- scoring -------------------------------------------------------------------------------


def test_score_rewards_recency_and_corroboration():
    stale = make(signals={"recent_repos_own": 3, "latest_push": "2026-03-01T00:00:00Z",
                          "languages": ["Go"]})
    fresh = make(signals={"recent_repos_own": 3, "latest_push": "2026-08-15T00:00:00Z",
                          "languages": ["Go"]})
    assert score_candidate(fresh, today_iso=TODAY) > score_candidate(stale, today_iso=TODAY)

    plain = make()
    corroborated = make(signals={"recent_repos_own": 3, "latest_push": "2026-08-10T10:00:00Z",
                                 "languages": ["Go", "Python"],
                                 "peppol_match": {"is_kvk": True},
                                 "careers_dev_terms": ["developer"]})
    assert score_candidate(corroborated, today_iso=TODAY) > score_candidate(plain, today_iso=TODAY)


def test_score_breakdown_is_auditable():
    cand = make()
    score_candidate(cand, today_iso=TODAY)
    breakdown = cand.signals["score_breakdown"]
    assert abs(sum(breakdown.values()) - cand.score) < 1e-6


# --- peppol matching -----------------------------------------------------------------------


def test_peppol_match_requires_exact_normalised_name():
    matches = [
        {
            "participantID": {"value": "0106:14075247"},
            "entities": [{"name": [{"name": "Voorbeeld B.V."}], "countryCode": "NL", "regDate": "2020-01-01"}],
        }
    ]
    assert peppol.best_nl_match(matches, "Voorbeeld")["is_kvk"] is True
    assert peppol.best_nl_match(matches, "Voorbeeld Software") is None


def test_peppol_ignores_foreign_entities():
    matches = [
        {
            "participantID": {"value": "9925:be0443243082"},
            "entities": [{"name": [{"name": "Voorbeeld"}], "countryCode": "BE"}],
        }
    ]
    assert peppol.best_nl_match(matches, "Voorbeeld") is None


def test_peppol_match_is_flagged_for_verification():
    matches = [
        {
            "participantID": {"value": "0106:14075247"},
            "entities": [{"name": [{"name": "Voorbeeld"}], "countryCode": "NL"}],
        }
    ]
    assert peppol.best_nl_match(matches, "Voorbeeld")["verify_before_use"] is True


# --- window partitioning -------------------------------------------------------------------


def test_windows_tile_the_range_without_gaps_or_overlap():
    windows = gh.month_windows("2020-01-01", "2021-12-31", 6)
    assert windows[0][0] == "2020-01-01"
    assert windows[-1][1] == "2021-12-31"
    for (_, end), (start, _) in zip(windows, windows[1:]):
        import datetime as dt

        assert dt.date.fromisoformat(start) - dt.date.fromisoformat(end) == dt.timedelta(days=1)


# --- rules added after the first live run ---------------------------------------------------
# Each of these was written because a real candidate got through and should not have.


def test_university_lab_is_excluded_by_website_host():
    """`ai4mde.liacs.nl` survived the first live run; LIACS is Leiden's CS institute."""
    cand = make(display_name="AI4MDE", website="https://ai4mde.liacs.nl")
    apply_exclusions(cand, CFG)
    assert any("kennisinstelling" in r for r in cand.exclusions)


@pytest.mark.parametrize(
    "website",
    ["https://www.tudelft.nl/lab", "https://x.uva.nl", "https://mit.edu", "https://cam.ac.uk"],
)
def test_academic_hosts_are_recognised(website):
    assert academic_host(website) is not None


@pytest.mark.parametrize(
    "website", ["https://codar.nl", "https://datastudy.nl", "https://badge.team", None]
)
def test_ordinary_hosts_are_not_academic(website):
    assert academic_host(website) is None


def test_volunteer_association_is_excluded():
    """A scouting group survived the first live run. It has no S&O wage base."""
    cand = make(display_name="Scouting Rudyard Kipling Nuenen")
    apply_exclusions(cand, CFG)
    assert any("vereniging" in r for r in cand.exclusions)


@pytest.mark.parametrize(
    "title",
    ["ExOrtis.com is available", "Virenix - Coming Soon", "This domain is for sale",
     "Apache2 Ubuntu Default Page", "Index of /"],
)
def test_parked_or_unbuilt_site_is_excluded(title):
    cand = make(signals={"recent_repos_own": 2, "enriched": True, "website_title": title})
    apply_exclusions(cand, CFG)
    assert any("geparkeerd" in r for r in cand.exclusions), title


def test_real_company_title_is_not_flagged_as_parked():
    cand = make(signals={"recent_repos_own": 2, "enriched": True,
                         "website_title": "Codar B.V. | Senior Kubernetes and Cloud Native Consultancy"})
    apply_exclusions(cand, CFG)
    assert cand.exclusions == []


def test_review_flags_surface_doubts_without_excluding():
    cand = make(public_email=None, signals={"recent_repos_own": 1, "enriched": True,
                                            "website_title": ""})
    apply_exclusions(cand, CFG)
    flags = cand.signals["review_flags"]
    assert cand.exclusions == []
    assert any("Peppol" in f for f in flags)
    assert any("dun bewijs" in f for f in flags)
    assert any("paginatitel" in f for f in flags)
    assert any("e-mailadres" in f for f in flags)


def test_strong_candidate_has_few_flags():
    cand = make(signals={"recent_repos_own": 4, "enriched": True, "website_title": "Codar B.V.",
                         "careers_dev_terms": ["developer"], "peppol_match": {"is_kvk": True}})
    apply_exclusions(cand, CFG)
    assert cand.signals["review_flags"] == []


def test_marketing_community_copy_does_not_exclude_a_real_company():
    """'Join our community' on a homepage is not evidence of a volunteer association."""
    cand = make(display_name="Codar B.V.",
                signals={"recent_repos_own": 3, "enriched": True,
                         "website_title": "Codar B.V. — join our developer community"})
    apply_exclusions(cand, CFG)
    assert cand.exclusions == []


def test_school_homepage_raises_a_flag_not_a_silent_pass():
    """Aventus (an MBO college) survived the wide run; its homepage title says "De school ...".

    A flag rather than an exclusion, because "school" also appears on companies that sell to schools.
    """
    cand = make(display_name="Aventus, Deventer",
                signals={"recent_repos_own": 2, "enriched": True,
                         "website_title": "De school waar jij 't maakt | Aventus"})
    apply_exclusions(cand, CFG)
    assert cand.exclusions == []
    assert any("onderwijs" in f for f in cand.signals["review_flags"])


def test_named_education_institutions_are_excluded_outright():
    for name in ("ROC Midden Nederland", "Scholengemeenschap Zuid", "Onderwijsgroep Tilburg"):
        cand = make(display_name=name)
        apply_exclusions(cand, CFG)
        assert any("publieke" in r for r in cand.exclusions), name
