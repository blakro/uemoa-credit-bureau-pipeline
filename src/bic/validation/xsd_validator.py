"""Validation structurelle des fichiers de déclaration via le schéma XSD.

Traduit les erreurs lxml (en anglais, cryptiques) en rejets exploitables,
avec un code d'anomalie déduit de l'élément et du type de violation quand
c'est possible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from lxml import etree

CHEMIN_XSD_DEFAUT = Path(__file__).resolve().parents[3] / "schemas" / "declaration_bic_v1.xsd"

#: Association élément XML -> code d'anomalie, pour les violations de type/valeur.
_CODE_PAR_ELEMENT_LEXICAL: dict[str, str] = {
    "date_naissance": "E002",
    "date_octroi": "E002",
    "date_echeance": "E002",
    "date_arrete": "E002",
    "montant_octroye": "E003",
    "encours": "E003",
    "montant_impaye": "E003",
    "taux_interet": "E003",
    "montant_garantie": "E003",
}
#: Association élément XML -> code d'anomalie, pour les violations de facette (plage/motif/énum).
_CODE_PAR_ELEMENT_FACETTE: dict[str, str] = {
    "encours": "E004",
    "devise": "E006",
    "numero_piece": "E010",
    "telephone": "E014",
}

_MESSAGES_FR: dict[str, str] = {
    "E002": (
        "La date fournie n'est pas dans un format valide (attendu : AAAA-MM-JJ) "
        "ou correspond à une date calendaire impossible."
    ),
    "E003": "Ce montant n'est pas une valeur numérique valide.",
    "E004": "L'encours ne peut pas être négatif.",
    "E006": "Devise non autorisée : seule la devise XOF est acceptée pour une déclaration UEMOA.",
    "E010": "Numéro de pièce d'identité au format invalide (ex. attendu : NE-CNI-12345678).",
    "E014": "Le numéro de téléphone ne respecte pas le format national attendu (+227XXXXXXXX).",
}


@dataclass(frozen=True)
class Rejet:
    """Un rejet structurel détecté par la validation XSD."""

    ligne: int
    colonne: int
    code: str
    message: str


@lru_cache(maxsize=1)
def _charger_schema(chemin_xsd: Path = CHEMIN_XSD_DEFAUT) -> etree.XMLSchema:
    """Charge (et met en cache) le schéma XSD depuis le disque."""
    with chemin_xsd.open("rb") as f:
        doc = etree.parse(f)
    return etree.XMLSchema(doc)


def _nom_element(chemin_erreur: str) -> str:
    """Extrait le nom du dernier élément mentionné dans le path d'une erreur lxml."""
    dernier_segment = chemin_erreur.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"\[\d+\]$", "", dernier_segment)


def _traduire_erreur(erreur: etree._LogEntry) -> Rejet:
    """Traduit une entrée d'erreur lxml en `Rejet` avec code et message français."""
    element = _nom_element(erreur.path or "")
    message_brut = erreur.message

    code = None
    if "facet" in message_brut or "enumeration" in message_brut:
        code = _CODE_PAR_ELEMENT_FACETTE.get(element)
    if code is None:
        code = _CODE_PAR_ELEMENT_LEXICAL.get(element)
    if code is None:
        code = _CODE_PAR_ELEMENT_FACETTE.get(element, "E000")

    message = _MESSAGES_FR.get(
        code, f"Erreur de structure XML sur l'élément « {element} » : {message_brut}"
    )

    return Rejet(
        ligne=erreur.line, colonne=getattr(erreur, "column", 0) or 0, code=code, message=message
    )


def valider_structure(contenu_xml: bytes, chemin_xsd: Path = CHEMIN_XSD_DEFAUT) -> list[Rejet]:
    """Valide `contenu_xml` contre le schéma XSD et retourne la liste des rejets structurels."""
    schema = _charger_schema(chemin_xsd)
    try:
        arbre = etree.fromstring(contenu_xml)
    except etree.XMLSyntaxError as erreur:
        return [
            Rejet(
                ligne=erreur.lineno or 0,
                colonne=erreur.offset or 0,
                code="E000",
                message=f"Fichier XML mal formé : {erreur.msg}",
            )
        ]

    if schema.validate(arbre):
        return []

    return [_traduire_erreur(erreur) for erreur in schema.error_log]
