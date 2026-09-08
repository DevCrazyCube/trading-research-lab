"""The Dutch briefing: one page, every claim linked, no eligibility asserted.

The briefing exists to answer a question the reader will ask in the first three seconds — *why are
you writing to me specifically?* — with public URLs they can open, and then to be honest about the
part we cannot see. Its structure follows that:

    why you                -> the evidence, each line with a link and an observation date
    what the WBSO is       -> RVO's parameters, quoted, with the RVO URL
    a worked example       -> our assumptions, labelled as ours, with the arithmetic shown
    what actually decides  -> RVO's own conditions, which is where a public repo stops being proof
    what we do not know    -> the uncertainty paragraph
    the deadlines          -> RVO's rule, with the caveat that the 2027 calendar is unpublished
    doing it without us    -> the WBSO-wijzer and mijn.rvo.nl, said plainly
    sender / opt-out       -> Telecommunicatiewet 11.7 and AVG identity, opt-out, lawful basis

Two artefacts are produced per candidate: the briefing (what the owner may send after reading it)
and a dossier (what the owner needs to check before sending). Anything uncertain — the Peppol
identity match above all — goes in the dossier and never in the briefing.
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import Any

from .benefit import Scenario, eur, nl_int, scenario_ladder, zelfstandige_bedrag
from .ethics import lint_briefing
from .model import Candidate
from .params import WbsoParams

PLACEHOLDER_RE = re.compile(r"<<INVULLEN[^>]*>>")

CONCEPT_BANNER = (
    "> **CONCEPT — NIET VERZENDEN.** Dit bestand is automatisch gegenereerd uit openbare bronnen "
    "en is nog niet door een mens gelezen. Er is niets verstuurd. Controleer elke regel en elke "
    "bron voordat dit ooit een e-mail wordt.\n"
)


def load_sender(path: pathlib.Path | str) -> dict[str, Any]:
    doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    doc["_placeholders"] = sorted(
        {v for v in doc.values() if isinstance(v, str) and PLACEHOLDER_RE.search(v)}
    )
    doc["_ready_to_send"] = not doc["_placeholders"]
    return doc


def estimate_developers(cand: Candidate) -> tuple[int, str]:
    """A deliberately conservative headcount guess, with the reasoning returned alongside it.

    Public repositories do not reveal headcount. What they reveal is that *at least one person*
    writes code here. Anything beyond that is inference, so the estimate starts at 1 and only rises
    on a second independent public signal (a careers page advertising developer roles).
    """
    own = int(cand.signals.get("recent_repos_own") or 0)
    reasons = [f"{own} eigen publieke repositor{'y' if own == 1 else 'ies'} met recente commits"]
    devs = 1
    if cand.signals.get("careers_dev_terms"):
        devs = 2
        reasons.append("een eigen vacaturepagina met ontwikkelfuncties")
    return devs, "; ".join(reasons)


NL_MONTHS = (
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
)


def nl_date(iso: str) -> str:
    """2026-09-30 -> '30 september 2026'. An ISO date in a Dutch business letter reads as a machine."""
    import datetime as dt

    try:
        d = dt.date.fromisoformat(iso[:10])
    except ValueError:
        return iso
    return f"{d.day} {NL_MONTHS[d.month - 1]} {d.year}"


def _evidence_lines(cand: Candidate) -> list[str]:
    lines = []
    for ev in cand.evidence:
        if ev.source == "peppol":
            continue  # identity corroboration is dossier-only; see module docstring
        date = ev.observed_utc[:10]
        lines.append(f"- {ev.claim_nl} (bron: {ev.url} — door ons bekeken op {date})")
    return lines


def _scenario_table(scenarios: list[Scenario]) -> str:
    head = (
        "| aanname S&O-uren | loonkosten (uren x uurloon) | forfait kosten | S&O-grondslag | "
        "reken-uitkomst WBSO |\n|---|---|---|---|---|\n"
    )
    rows = "".join(
        f"| {s.so_uren} | {eur(s.loonkosten)} | {eur(s.kosten_component)} | {eur(s.grondslag)} | "
        f"{eur(s.voordeel)} |\n"
        for s in scenarios
    )
    return head + rows


def render_briefing(cand: Candidate, p: WbsoParams, sender: dict[str, Any], *, today_iso: str) -> str:
    devs, dev_reason = estimate_developers(cand)
    scenarios = scenario_ladder(p, developers=devs, starter=False)
    zzp = zelfstandige_bedrag(p, starter=False)
    zzp_starter = zelfstandige_bedrag(p, starter=True)
    naam = cand.display_name or cand.github_login
    evidence_lines = _evidence_lines(cand)

    deadline_jan = p.deadlines["voor_ingangsdatum_1_januari_2027"]
    deadline_okt = p.deadlines["voor_extra_aanvraag_okt_dec_2026"]

    parts: list[str] = []
    parts.append(f"# WBSO — publieke signalen bij {naam}\n")
    parts.append(CONCEPT_BANNER)
    parts.append(
        f"*Gegenereerd op {today_iso} · kandidaat-id `{cand.candidate_id}` · "
        f"score {cand.score} · RVO-parameters bevroren op {p.frozen_on.isoformat()}*\n"
    )
    parts.append("---\n")
    parts.append(f"**Onderwerp:** WBSO 2027 — wat wij publiek zagen bij {naam}, en wat dat wel en niet betekent\n")
    parts.append("Geachte heer, mevrouw,\n")

    parts.append(
        "Wij zoeken in openbare bronnen naar Nederlandse bedrijven die zichtbaar software "
        "ontwikkelen, omdat een deel daarvan **mogelijk in aanmerking** komt voor de WBSO — de "
        "fiscale regeling voor speur- en ontwikkelingswerk — en die regeling niet gebruikt. "
        "Of dat voor u geldt, weten wij niet. Wat wij wél hebben, staat hieronder, met bronnen "
        "erbij zodat u het zelf kunt nakijken.\n"
    )

    parts.append("## 1. Waarom juist u dit bericht krijgt\n")
    parts.append(
        "Dit zijn de openbare signalen die wij bij uw organisatie vonden. Alles hieronder is "
        "publiek; wij hebben niets ingezien wat niet voor iedereen zichtbaar is.\n"
    )
    parts.append("<!--EVIDENCE-START-->")
    parts.extend(evidence_lines)
    parts.append("<!--EVIDENCE-END-->\n")
    parts.append(
        "Dit toont **zichtbare ontwikkelactiviteit**. Het toont niet dat dat werk aan de "
        "WBSO-voorwaarden voldoet — dat hangt af van feiten die wij niet kunnen zien (§4).\n"
    )

    parts.append("## 2. Wat de WBSO in 2026 oplevert — cijfers van RVO\n")
    parts.append(
        f"| parameter | waarde {p.scheme_year} |\n|---|---|\n"
        f"| tarief 1e schijf | {p.tarief_schijf1:.0%} van de S&O-grondslag |\n"
        f"| tarief 1e schijf, starters | {p.tarief_schijf1_starters:.0%} |\n"
        f"| grens 1e schijf | {eur(p.grens_schijf1)} S&O-grondslag |\n"
        f"| tarief 2e schijf | {p.tarief_schijf2:.0%} |\n"
        f"| S&O-aftrek zelfstandigen (geen personeel) | {eur(zzp)}, starters {eur(zzp_starter)} |\n"
    )
    parts.append(
        f"Bron: RVO, {p.sources[0]['url']} — door ons gelezen op {p.sources[0]['accessed_utc'][:10]}. "
        "Wij zijn geen onderdeel van RVO of de Belastingdienst en spreken niet voor hen.\n"
    )
    parts.append(
        f"**Let op:** dit zijn de parameters voor **{p.scheme_year}**. RVO stelt de tarieven per "
        "jaar vast en had die voor 2027 op onze leesdatum nog niet gepubliceerd. Een aanvraag met "
        "ingangsdatum 1 januari 2027 wordt dus afgerekend tegen cijfers die nu nog niet vaststaan.\n"
    )

    parts.append("## 3. Een rekenvoorbeeld — met ónze aannames, niet uw cijfers\n")
    parts.append(
        f"Wij kennen uw uren, loonkosten en projecten niet. Om te laten zien om welke orde van "
        f"grootte het gaat, rekenen wij met een **aanname**: {devs} ontwikkelaar(s) — gebaseerd op "
        f"{dev_reason} — en het RVO-standaard S&O-uurloon van {eur(p.default_uurloon)} dat geldt "
        f"als u in 2024 geen WBSO gebruikte. De kostencomponent is het RVO-forfait: "
        f"{eur(p.forfait_per_uur_tot_1800)} per S&O-uur tot {nl_int(p.forfait_drempel_uren)} uur, "
        f"daarboven {eur(p.forfait_per_uur_boven_1800)}.\n"
    )
    parts.append(_scenario_table(scenarios))
    parts.append(
        f"De rekenregel is die van RVO zelf: S&O-grondslag = (S&O-uren × S&O-uurloon) + kosten; "
        f"voordeel = {p.tarief_schijf1:.0%} over de eerste {eur(p.grens_schijf1)} en "
        f"{p.tarief_schijf2:.0%} daarboven. U kunt dit natrekken op "
        "https://www.rvo.nl/subsidies-financiering/wbso/bereken-wbso-voordeel.\n"
    )
    parts.append(
        "**Dit is een rekenvoorbeeld en geen toezegging.** Andere uren geven een andere uitkomst, "
        "en of er überhaupt een uitkomst is, beslist RVO — niet wij.\n"
    )

    parts.append("## 4. Waar het werkelijk op vastzit\n")
    parts.append(
        "RVO stelt voorwaarden die niets met zichtbaarheid te maken hebben. De belangrijkste, in "
        "RVO's eigen woorden:\n"
    )
    for quote in p.voorwaarden_quotes[:6]:
        parts.append(f"> {quote}\n")
    parts.append(
        "De zin die er in de praktijk het meest toe doet is *“technisch nieuw voor uw bedrijf”*. "
        "Routinematig bouwen met bekende technieken telt niet, hoe hard er ook gewerkt wordt. "
        "Een publieke repository laat activiteit zien, geen technische onzekerheid.\n"
    )

    parts.append("## 5. Wat wij niet weten\n")
    parts.append(
        "Wij hebben uw administratie niet gezien, uw projecten niet beoordeeld en uw fiscale "
        "positie niet bekeken. Wij weten niet hoeveel uren aan S&O opgaan, of u loonheffing "
        "afdraagt voor de mensen die dit werk doen, of u al WBSO gebruikt of aanvroeg, en of uw "
        "werk technisch nieuw is voor uw bedrijf. Dit bericht is dan ook **geen advies en geen "
        "beoordeling** — het is een signaal uit openbare bronnen, met de aanname er expliciet bij. "
        "Als u de WBSO al gebruikt of eerder een afwijzing kreeg, is dit bericht voor u niet "
        "relevant en horen wij dat graag, dan schrappen wij u.\n"
    )

    parts.append("## 6. De data die er wél toe doen\n")
    parts.append(
        f"- **{nl_date(deadline_okt)}** — uiterste datum voor een (extra) aanvraag over de periode "
        "oktober–december 2026.\n"
        f"- **{nl_date(deadline_jan)}** — RVO's staande regel is: wilt u vanaf 1 januari gebruikmaken van de "
        "WBSO, dien dan uiterlijk 20 december in. Voor 2027 heeft RVO de kalender op onze "
        "leesdatum nog niet gepubliceerd; controleer "
        "https://www.rvo.nl/subsidies-financiering/wbso/kalender.\n"
        "- De WBSO geldt alleen voor **toekomstig** S&O-werk. Werk dat al af is, telt niet meer.\n"
    )

    parts.append("## 7. Dit kunt u zelf doen, zonder ons\n")
    parts.append(
        "De WBSO is geen regeling waar een adviseur voor nodig is. U kunt zelf aanvragen via "
        "mijn.rvo.nl (met eHerkenning), en RVO heeft een gratis WBSO-wijzer waarmee u in een paar "
        "minuten ziet of u aan de basisvoorwaarden voldoet: "
        "https://www.rvo.nl/subsidies-financiering/wbso/wbso-wijzer. "
        "Wij zeggen dit erbij omdat het waar is; als u het zelf doet, is dit bericht alsnog nuttig "
        "geweest.\n"
    )

    tarief = sender.get("tarief_regel") or ""
    if tarief and not PLACEHOLDER_RE.search(tarief):
        parts.append("## 8. Als u wél hulp wilt\n")
        parts.append(f"{tarief}\n")

    parts.append("---\n")
    parts.append("### Afzender en afmelden\n")
    parts.append(
        f"**Afzender:** {sender.get('afzender_naam')} — {sender.get('handelsnaam')}, "
        f"KVK {sender.get('kvk_nummer')}, {sender.get('adres')}, "
        f"{sender.get('postcode_plaats')}, {sender.get('land', 'Nederland')}. "
        f"E-mail {sender.get('email')}, telefoon {sender.get('telefoon')}.\n"
    )
    parts.append(
        "**Waarom u dit ontvangt:** u ontvangt dit op een zakelijk adres dat uw organisatie zelf "
        "openbaar heeft gemaakt. Wij verwerken alleen zakelijke contactgegevens uit openbare "
        "bronnen (grondslag: gerechtvaardigd belang, AVG art. 6 lid 1 sub f) en bewaren die "
        "maximaal 12 maanden na het laatste contact.\n"
    )
    parts.append(f"**Afmelden:** {sender.get('afmelden_instructie')}\n")
    parts.append(
        f"**Privacyverklaring:** {sender.get('privacyverklaring_url')}. "
        "Wij zijn een onafhankelijke partij en handelen niet namens een overheidsinstantie.\n"
    )
    return "\n".join(parts)


def render_dossier(cand: Candidate, p: WbsoParams, *, today_iso: str) -> dict[str, Any]:
    """Everything the owner must check before this briefing may be sent. Never shown to the reader."""
    peppol_match = cand.signals.get("peppol_match")
    checks = [
        "Is dit een Nederlandse onderneming (geen buitenlands filiaal, geen publieke instelling)?",
        "Klopt het e-mailadres, en is het een zakelijk (geen persoonlijk) adres?",
        "Zijn de genoemde repositories echt van dit bedrijf en niet van een naamgenoot?",
        "Staat dit bedrijf niet op de blokkeerlijst / heeft het niet eerder afgemeld?",
        "Is de RVO-parameterbron nog geldig (bevriezingsdatum hieronder) en de kalender voor 2027 gecontroleerd?",
        "Klopt de aanname over het aantal ontwikkelaars ruwweg, of moet die naar beneden?",
    ]
    if peppol_match:
        checks.insert(
            1,
            f"Peppol vond een NL-entiteit met dezelfde naam ({peppol_match.get('participant_id')}). "
            "Dit is een NAAMovereenkomst, geen identiteitsbewijs — verifieer bij kvk.nl voordat u "
            "hier iets op baseert. Dit nummer staat bewust NIET in de briefing.",
        )
    return {
        "candidate_id": cand.candidate_id,
        "display_name": cand.display_name,
        "github": cand.github_url,
        "website": cand.website,
        "public_email": cand.public_email,
        "location_text": cand.location_text,
        # Doubts no rule could settle, put first because they are the reason a human reads this file.
        "review_flags": cand.signals.get("review_flags", []),
        "score": cand.score,
        "score_breakdown": cand.signals.get("score_breakdown"),
        "signals": {k: v for k, v in cand.signals.items() if k != "score_breakdown"},
        "exclusions": cand.exclusions,
        "evidence": [e.as_dict() for e in cand.evidence],
        "owner_checklist": checks,
        "params_frozen_on": p.frozen_on.isoformat(),
        "generated": today_iso,
        "sent": False,
        "sendable": False,
        "sendable_reason": "sender profile carries placeholders; owner has not registered KVK",
    }


def evidence_urls(cand: Candidate, sender: dict[str, Any]) -> list[str]:
    """URLs the linter may see in a briefing: the candidate's evidence, plus the sender's own.

    Sender values are scanned with the same URL regex the linter uses, so a placeholder such as
    `<<INVULLEN: https://voorbeeld.nl>>` still yields the URL inside it and does not read as an
    unsourced company claim.
    """
    from .ethics import URL_RE

    urls = [e.url for e in cand.evidence if e.url]
    for val in sender.values():
        if isinstance(val, str):
            urls.extend(u.rstrip("/.,") for u in URL_RE.findall(val))
    return urls


def generate(
    cand: Candidate,
    p: WbsoParams,
    sender: dict[str, Any],
    *,
    today_iso: str,
) -> tuple[str, dict[str, Any], Any]:
    text = render_briefing(cand, p, sender, today_iso=today_iso)
    dossier = render_dossier(cand, p, today_iso=today_iso)
    allowed = evidence_urls(cand, sender)
    result = lint_briefing(text, evidence_urls=allowed)
    # Recorded so `wbso.cli lint` reproduces exactly this verdict later, without needing the sender
    # profile that produced the briefing. A lint that cannot be re-run is a lint you have to trust.
    dossier["lint_allowed_urls"] = sorted(set(allowed))
    dossier["lint"] = result.as_dict()
    return text, dossier, result
