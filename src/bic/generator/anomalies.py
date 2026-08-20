"""Assemblage des déclarations et injection contrôlée d'anomalies, selon le profil du déclarant.

Chaque déclaration (un déclarant, un arrêté) est d'abord assemblée sous forme
d'enregistrements textuels bruts — la représentation la plus proche de ce qui
sera effectivement écrit dans le fichier XML. L'injection d'anomalies opère
directement sur ce texte : c'est ainsi qu'arrivent les données malformées en
conditions réelles. Chaque anomalie injectée est journalisée dans une liste
d'`AnomalieInjectee`, réutilisée en phase 3 pour mesurer le rappel du moteur
de règles.
"""

from __future__ import annotations

import datetime
import random
from dataclasses import dataclass, field

from bic.generator.profiles import ProfilDeclarant
from bic.generator.synthetic import (
    DERNIER_ARRETE,
    ContratRecord,
    EmprunteurRecord,
    JeuDeDonnees,
    SituationRecord,
)

#: Codes d'anomalie applicables à un enregistrement emprunteur.
_CODES_EMPRUNTEUR = ("E001", "E002", "E010", "E011", "E014")
#: Codes d'anomalie applicables à un enregistrement contrat/situation.
_CODES_CONTRAT = ("E002", "E003", "E004", "E005", "E006", "E007", "E008", "E012")


@dataclass(frozen=True)
class AnomalieInjectee:
    """Une anomalie volontairement injectée, journalisée pour évaluer le moteur de règles."""

    code_declarant: str
    entite: str
    ligne: str
    champ: str
    code: str


@dataclass
class DeclarationBrute:
    """Enregistrements textuels bruts d'une déclaration (un déclarant, un arrêté)."""

    code_declarant: str
    date_arrete: datetime.date
    emprunteurs: list[dict[str, str]] = field(default_factory=list)
    contrats: list[dict[str, str]] = field(default_factory=list)
    code_declarant_entete: str | None = None


def _valeur_str(valeur: object) -> str:
    return "" if valeur is None else str(valeur)


def _emprunteur_vers_champs(e: EmprunteurRecord) -> dict[str, str]:
    return {
        "id_emprunteur_source": e.id_emprunteur_source,
        "type_personne": e.type_personne,
        "nom": _valeur_str(e.nom),
        "prenom": _valeur_str(e.prenom),
        "raison_sociale": _valeur_str(e.raison_sociale),
        "date_naissance": _valeur_str(e.date_naissance.isoformat() if e.date_naissance else None),
        "sexe": _valeur_str(e.sexe),
        "type_piece": _valeur_str(e.type_piece),
        "numero_piece": _valeur_str(e.numero_piece),
        "nif": _valeur_str(e.nif),
        "telephone": _valeur_str(e.telephone),
        "ville": _valeur_str(e.ville),
        "pays": e.pays,
    }


def _contrat_situation_vers_champs(c: ContratRecord, s: SituationRecord) -> dict[str, str]:
    return {
        "id_contrat_source": c.id_contrat_source,
        "id_emprunteur_source": c.id_emprunteur_source,
        "type_credit": c.type_credit,
        "date_octroi": c.date_octroi.isoformat(),
        "date_echeance": c.date_echeance.isoformat(),
        "montant_octroye": f"{c.montant_octroye:.2f}",
        "devise": c.devise,
        "taux_interet": f"{c.taux_interet:.2f}",
        "periodicite": c.periodicite,
        "type_garantie": c.type_garantie,
        "montant_garantie": f"{c.montant_garantie:.2f}",
        "date_arrete": s.date_arrete.isoformat(),
        "encours": f"{s.encours:.2f}",
        "montant_impaye": f"{s.montant_impaye:.2f}",
        "jours_retard": str(s.jours_retard),
        "classification": s.classification,
    }


def assembler_declarations(jeu: JeuDeDonnees) -> list[DeclarationBrute]:
    """Regroupe le jeu de données par (déclarant, arrêté) en enregistrements textuels bruts."""
    emprunteurs_par_cle = {(e.code_declarant, e.id_emprunteur_source): e for e in jeu.emprunteurs}
    contrats_par_cle = {(c.code_declarant, c.id_contrat_source): c for c in jeu.contrats}

    groupes: dict[tuple[str, datetime.date], DeclarationBrute] = {}
    emprunteurs_inclus: dict[tuple[str, datetime.date], set[str]] = {}

    for situation in jeu.situations:
        contrat = contrats_par_cle[(situation.code_declarant, situation.id_contrat_source)]
        emprunteur = emprunteurs_par_cle[(contrat.code_declarant, contrat.id_emprunteur_source)]
        cle = (situation.code_declarant, situation.date_arrete)

        if cle not in groupes:
            groupes[cle] = DeclarationBrute(
                code_declarant=situation.code_declarant, date_arrete=situation.date_arrete
            )
            emprunteurs_inclus[cle] = set()

        declaration = groupes[cle]
        if emprunteur.id_emprunteur_source not in emprunteurs_inclus[cle]:
            declaration.emprunteurs.append(_emprunteur_vers_champs(emprunteur))
            emprunteurs_inclus[cle].add(emprunteur.id_emprunteur_source)
        declaration.contrats.append(_contrat_situation_vers_champs(contrat, situation))

    return [groupes[cle] for cle in sorted(groupes, key=lambda k: (k[0], k[1]))]


def _il_y_a_ans(ans: int) -> str:
    return DERNIER_ARRETE.replace(year=DERNIER_ARRETE.year - ans).isoformat()


def _injecter_anomalie_emprunteur(
    rng: random.Random,
    code_declarant: str,
    emprunteur: dict[str, str],
    journal: list[AnomalieInjectee],
) -> None:
    candidats = list(_CODES_EMPRUNTEUR)
    if emprunteur["type_personne"] == "PM":
        candidats.append("E015")
    code = rng.choice(candidats)
    ligne = emprunteur["id_emprunteur_source"]
    champ = "id_emprunteur_source"

    if code == "E001":
        champ = "nom" if emprunteur["type_personne"] == "PP" else "raison_sociale"
        emprunteur[champ] = ""
    elif code == "E002":
        champ = "date_naissance"
        emprunteur[champ] = "31/02/2020"
    elif code == "E010":
        champ = "numero_piece"
        emprunteur[champ] = "PIECE-INVALIDE"
    elif code == "E011":
        champ = "date_naissance"
        emprunteur[champ] = _il_y_a_ans(rng.choice([5, 110]))
    elif code == "E014":
        champ = "telephone"
        emprunteur[champ] = "0612345678"
    elif code == "E015":
        champ = "nif"
        emprunteur[champ] = ""

    journal.append(AnomalieInjectee(code_declarant, "emprunteur", ligne, champ, code))


def _injecter_anomalie_contrat(
    rng: random.Random,
    code_declarant: str,
    contrat: dict[str, str],
    journal: list[AnomalieInjectee],
) -> None:
    code = rng.choice(_CODES_CONTRAT)
    ligne = contrat["id_contrat_source"]
    champ = "id_contrat_source"

    if code == "E002":
        champ = rng.choice(["date_octroi", "date_echeance"])
        contrat[champ] = "31/02/2024"
    elif code == "E003":
        champ = rng.choice(["montant_octroye", "encours"])
        contrat[champ] = "N/A"
    elif code == "E004":
        champ = "encours"
        contrat[champ] = f"-{abs(float(contrat['encours'])) + 1000:.2f}"
    elif code == "E005":
        champ = "encours"
        contrat[champ] = f"{float(contrat['montant_octroye']) * 1.5:.2f}"
    elif code == "E006":
        champ = "devise"
        contrat[champ] = rng.choice(["EUR", "USD", "GHS"])
    elif code == "E007":
        champ = "date_echeance"
        octroi = datetime.date.fromisoformat(contrat["date_octroi"])
        contrat[champ] = (octroi - datetime.timedelta(days=30)).isoformat()
    elif code == "E008":
        champ = "id_emprunteur_source"
        contrat[champ] = "EMP999999"
    elif code == "E012":
        champ = "classification"
        autres = [
            c
            for c in ("sain", "sensible", "douteux", "contentieux")
            if c != contrat["classification"]
        ]
        contrat[champ] = rng.choice(autres)

    journal.append(AnomalieInjectee(code_declarant, "contrat", ligne, champ, code))


def injecter_anomalies(
    declarations: list[DeclarationBrute], profiles: list[ProfilDeclarant], seed: int
) -> tuple[list[DeclarationBrute], list[AnomalieInjectee]]:
    """Corrompt une fraction des champs de chaque déclaration, selon le profil de son déclarant."""
    rng = random.Random(seed)
    profil_par_code = {p.code_declarant: p for p in profiles}
    journal: list[AnomalieInjectee] = []

    for declaration in declarations:
        taux = profil_par_code[declaration.code_declarant].taux_anomalie

        for emprunteur in declaration.emprunteurs:
            if rng.random() < taux:
                _injecter_anomalie_emprunteur(rng, declaration.code_declarant, emprunteur, journal)

        for contrat in declaration.contrats:
            if rng.random() < taux:
                _injecter_anomalie_contrat(rng, declaration.code_declarant, contrat, journal)

        if len(declaration.contrats) >= 2 and rng.random() < taux:
            a, b = rng.sample(declaration.contrats, 2)
            b["id_contrat_source"] = a["id_contrat_source"]
            journal.append(
                AnomalieInjectee(
                    declaration.code_declarant,
                    "contrat",
                    b["id_contrat_source"],
                    "id_contrat_source",
                    "E009",
                )
            )

        if rng.random() < taux:
            declaration.code_declarant_entete = f"XX{rng.randint(1000, 9999)}"
            journal.append(
                AnomalieInjectee(
                    declaration.code_declarant,
                    "entete",
                    declaration.code_declarant,
                    "code_declarant",
                    "E013",
                )
            )

    return declarations, journal
