"""The arithmetic is only allowed in a briefing because this file proves it against RVO's own output.

RVO publishes three worked examples on its benefit page. If our formula reproduces all three to the
euro, then the formula is RVO's formula and not our interpretation of it. If a future parameter edit
breaks any of them, no briefing can be generated until it is fixed.
"""
from __future__ import annotations

import pytest

from wbso.benefit import (
    build_scenario,
    eur,
    forfait_kosten,
    scenario_ladder,
    voordeel_from_grondslag,
    zelfstandige_bedrag,
)
from wbso.params import ParameterError, load_params

P = load_params()


@pytest.mark.parametrize("example", P.worked_examples, ids=lambda e: e["id"])
def test_reproduces_rvo_worked_examples(example):
    """Every published RVO situation, to the euro."""
    scenario = build_scenario(
        P,
        label=example["id"],
        so_uren=example["so_uren"],
        starter=example["starter"],
        uurloon=example["so_uurloon_eur"],
        kosten_mode=example["kosten_mode"],
        werkelijke_kosten=example.get("werkelijke_kosten_eur", 0),
    )
    assert scenario.voordeel == example["expected_voordeel_eur"], (
        f"{example['id']}: computed {scenario.voordeel}, RVO publishes "
        f"{example['expected_voordeel_eur']} — the formula no longer matches the source"
    )


def test_forfait_two_tier():
    assert forfait_kosten(1800, P) == 18_000
    assert forfait_kosten(1801, P) == 18_004
    assert forfait_kosten(0, P) == 0


def test_bracket_boundary_is_continuous():
    """No jump at the schijf boundary: the second bracket applies only to the excess."""
    at = voordeel_from_grondslag(P.grens_schijf1, P)
    just_over = voordeel_from_grondslag(P.grens_schijf1 + 1000, P)
    assert just_over - at == pytest.approx(1000 * P.tarief_schijf2)
    assert at == pytest.approx(P.grens_schijf1 * P.tarief_schijf1)


def test_starter_rate_is_higher_only_in_first_bracket():
    g = P.grens_schijf1 * 2
    normal = voordeel_from_grondslag(g, P, starter=False)
    starter = voordeel_from_grondslag(g, P, starter=True)
    delta = (P.tarief_schijf1_starters - P.tarief_schijf1) * P.grens_schijf1
    assert starter - normal == pytest.approx(delta)


def test_zelfstandige_amounts_come_from_params():
    assert zelfstandige_bedrag(P) == P.aftrek_zelfstandigen
    assert zelfstandige_bedrag(P, starter=True) == (
        P.aftrek_zelfstandigen + P.aftrek_zelfstandigen_starters_extra
    )


def test_ladder_is_monotonic_and_carries_its_assumptions():
    ladder = scenario_ladder(P, developers=2)
    assert [s.voordeel for s in ladder] == sorted(s.voordeel for s in ladder)
    for s in ladder:
        assert "aanname" in s.assumption_nl
        assert str(s.so_uren) in s.assumption_nl


def test_negative_inputs_rejected():
    with pytest.raises(ValueError):
        forfait_kosten(-1, P)
    with pytest.raises(ValueError):
        voordeel_from_grondslag(-1, P)
    with pytest.raises(ValueError):
        build_scenario(P, label="x", so_uren=10, kosten_mode="onzin")


def test_eur_formats_dutch_thousands():
    """Dot thousands, no cents, and a non-breaking space so an amount cannot wrap away from its sign."""
    assert eur(391020) == "€ 391.020"
    assert eur(9750) == "€ 9.750"


def test_params_validation_rejects_broken_rate_ordering(tmp_path):
    import json

    doc = json.loads((P.raw and json.dumps(P.raw)))
    doc["rates"]["tarief_eerste_schijf"] = 0.9  # now above the starter rate
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ParameterError):
        load_params(path)


def test_every_parameter_has_a_source_quote():
    """A number without a quote is a number someone made up."""
    blob = " ".join(q for s in P.sources for q in s["quotes"])
    assert "36%" in blob and "50%" in blob and "16%" in blob
    assert "391.020" in blob
    assert "15.979" in blob and "7.996" in blob
    assert "29" in blob
    for src in P.sources:
        assert src["url"].startswith("https://www.rvo.nl/")
