"""The linter is the ethical spine's enforcement, so it gets adversarial tests, not happy paths.

Each `test_catches_*` writes the sentence a careless (or optimistic) generator would produce and
asserts the linter refuses it. If any of these ever passes silently, a stranger receives a false
claim about their tax position.
"""
from __future__ import annotations

import pytest

from wbso.ethics import lint_briefing

GOOD = """
# WBSO — publieke signalen bij Voorbeeld BV

U komt mogelijk in aanmerking voor de WBSO.

<!--EVIDENCE-START-->
- De publieke repository voorbeeld/tool had een commit op 2026-08-01. (bron: https://github.com/voorbeeld/tool)
<!--EVIDENCE-END-->

Rekenvoorbeeld op basis van een aanname. Dit is geen toezegging en geen advies.
Bron: https://www.rvo.nl/subsidies-financiering/wbso

Wat wij niet weten: uw uren, uw projecten, uw fiscale positie.
U kunt de WBSO ook zelf aanvragen via mijn.rvo.nl.

Afzender: Voorbeeld. Afmelden: antwoord met AFMELDEN.
"""

EVIDENCE = ["https://github.com/voorbeeld/tool"]


def lint(text: str):
    return lint_briefing(text, evidence_urls=EVIDENCE)


def test_reference_briefing_is_clean():
    result = lint(GOOD)
    assert result.ok, result.summary()


@pytest.mark.parametrize(
    "sentence",
    [
        "U komt in aanmerking voor de WBSO.",
        "Uw bedrijf kwalificeert voor de WBSO.",
        "U heeft recht op een teruggave.",
        "U ontvangt € 24.000 van de Belastingdienst.",
        "Uw WBSO-voordeel bedraagt € 24.000.",
        "Wij garanderen toekenning.",
        "Dit is gegarandeerd voordeel voor u.",
        "Wij regelen uw subsidie van begin tot eind.",
        "Wij schrijven u namens RVO.",
        "Laatste kans: dien vandaag in.",
        "You qualify for this scheme.",
        "Approval is guaranteed.",
    ],
)
def test_catches_forbidden_assertions(sentence):
    result = lint(GOOD + "\n" + sentence)
    assert not result.ok
    assert result.violations, f"linter allowed: {sentence!r}"


def test_hedged_sentence_is_allowed():
    """The hedge is what makes the sentence legitimate; it must not be over-blocked."""
    result = lint(GOOD + "\nU komt mogelijk in aanmerking voor de WBSO, dat kunnen wij niet zien.")
    assert result.ok, result.summary()


@pytest.mark.parametrize(
    "removed,key",
    [
        (("mogelijk in aanmerking",), "mogelijk_hedge"),
        # Both alternatives have to go: "geen advies" satisfies the same requirement as
        # "geen toezegging", which is the point of accepting either.
        (("geen toezegging", "geen advies"), "geen_toezegging"),
        (("https://www.rvo.nl/subsidies-financiering/wbso",), "rvo_link"),
        (("zelf aanvragen",), "zelf_doen"),
        (("aanname",), "aanname"),
        (("Wat wij niet weten",), "onzekerheid"),
        (("Afmelden", "AFMELDEN"), "afmelden"),
    ],
)
def test_catches_missing_disclosures(removed, key):
    text = GOOD
    for phrase in removed:
        text = text.replace(phrase, "XXX")
    result = lint(text)
    assert not result.ok
    assert key in {m["key"] for m in result.missing}, result.summary()


def test_catches_unsourced_company_url():
    """A repository we never observed must not be nameable in a briefing."""
    text = GOOD.replace(
        "<!--EVIDENCE-END-->",
        "- Ook zagen wij https://github.com/verzonnen/repo\n<!--EVIDENCE-END-->",
    )
    result = lint(text)
    assert not result.ok
    assert "https://github.com/verzonnen/repo" in result.unsourced_urls


def test_catches_evidence_claim_without_a_link():
    text = GOOD.replace(
        "<!--EVIDENCE-END-->",
        "- Uw team werkt aan machine learning.\n<!--EVIDENCE-END-->",
    )
    result = lint(text)
    assert not result.ok
    assert result.unlinked_claims


def test_missing_evidence_block_fails():
    text = GOOD.replace("<!--EVIDENCE-START-->", "").replace("<!--EVIDENCE-END-->", "")
    result = lint(text)
    assert not result.ok
    assert "NO EVIDENCE BLOCK MARKERS FOUND" in result.unlinked_claims


def test_rvo_and_kvk_urls_need_no_evidence_row():
    text = GOOD + "\nZie ook https://www.kvk.nl/inschrijven en https://www.rvo.nl/wbso-wijzer\n"
    assert lint(text).ok
